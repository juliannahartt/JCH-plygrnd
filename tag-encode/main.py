"""
tag-encode — BIB NFC Label Print & Encode
SATO CL4NX Plus 203dpi via direct USB (pyusb).
Copacker flavor list loaded from local JSON config (swappable to S3).
"""

import datetime
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, font as tkfont, filedialog, messagebox

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

import config_loader as cl
import sbpl_builder as sbpl
import usb_printer as usb_mod

# ─── Colors ───────────────────────────────────────────────────
BG      = "#1A1A2E"
PANEL   = "#16213E"
ACCENT  = "#0F3460"
GREEN   = "#00B894"
RED     = "#D63031"
YELLOW  = "#FDCB6E"
WHITE   = "#FFFFFF"
GRAY    = "#636E72"
SUBTEXT = "#B2BEC3"
DIM     = "#4A5568"


class TagEncodeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("tag-encode  |  BIB NFC Label Printer")
        self.configure(bg=BG)
        self.geometry("780x620")
        self.minsize(680, 540)
        self.resizable(True, True)

        self._provider = None
        self._flavors  = []
        self._printing = False

        self._build_ui()
        self.after(100, self._load_config_dialog)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ─── UI ───────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        content = tk.Frame(self, bg=BG)
        content.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=0)
        content.rowconfigure(1, weight=1)

        self._build_copacker_panel(content)
        self._build_job_panel(content)
        self._build_log_panel(content)
        self._build_statusbar()

    def _build_header(self):
        hdr = tk.Frame(self, bg=ACCENT, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        title_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        sub_font   = tkfont.Font(family="Segoe UI", size=9)

        tk.Label(hdr, text="tag-encode", font=title_font, bg=ACCENT, fg=WHITE).pack(side="left", padx=20, pady=6)
        tk.Label(hdr, text="BIB NFC Label Print & Encode", font=sub_font, bg=ACCENT, fg=SUBTEXT).pack(side="left", pady=6)

        self._printer_dot = tk.Label(hdr, text="●", font=tkfont.Font(size=12), bg=ACCENT, fg=GRAY)
        self._printer_dot.pack(side="right", padx=8)
        tk.Label(hdr, text="Printer", font=sub_font, bg=ACCENT, fg=SUBTEXT).pack(side="right")

        self._check_printer_btn = tk.Button(
            hdr, text="Check", font=sub_font, bg=PANEL, fg=WHITE,
            relief="flat", padx=8, pady=3, cursor="hand2",
            activebackground=BG, activeforeground=WHITE,
            command=self._check_printer,
        )
        self._check_printer_btn.pack(side="right", padx=4)

    def _build_copacker_panel(self, parent):
        panel = tk.Frame(parent, bg=PANEL)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=8)

        hf = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        lf = tkfont.Font(family="Segoe UI", size=9)
        vf = tkfont.Font(family="Consolas", size=12, weight="bold")

        tk.Label(panel, text="COPACKER", font=hf, bg=PANEL, fg=SUBTEXT).pack(anchor="w", padx=16, pady=(12, 4))
        ttk.Separator(panel, orient="horizontal").pack(fill="x", padx=16)

        self._copacker_name_var = tk.StringVar(value="No config loaded")
        self._copacker_id_var   = tk.StringVar(value="")

        tk.Label(panel, textvariable=self._copacker_name_var, font=vf, bg=PANEL, fg=WHITE).pack(anchor="w", padx=16, pady=(8, 2))
        tk.Label(panel, textvariable=self._copacker_id_var,   font=lf, bg=PANEL, fg=SUBTEXT).pack(anchor="w", padx=16, pady=(0, 8))

        tk.Button(
            panel, text="Load Different Config",
            font=lf, bg=ACCENT, fg=WHITE, relief="flat",
            activebackground=PANEL, activeforeground=WHITE,
            padx=10, pady=4, cursor="hand2",
            command=self._load_config_dialog,
        ).pack(anchor="w", padx=16, pady=(0, 12))

    def _build_job_panel(self, parent):
        panel = tk.Frame(parent, bg=PANEL)
        panel.grid(row=0, column=1, sticky="nsew", pady=8)

        hf    = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        lf    = tkfont.Font(family="Segoe UI", size=9)
        valf  = tkfont.Font(family="Consolas", size=11)
        bigf  = tkfont.Font(family="Segoe UI", size=14, weight="bold")

        tk.Label(panel, text="PRINT JOB", font=hf, bg=PANEL, fg=SUBTEXT).pack(anchor="w", padx=16, pady=(12, 4))
        ttk.Separator(panel, orient="horizontal").pack(fill="x", padx=16)

        # Flavor dropdown
        flavor_row = tk.Frame(panel, bg=PANEL)
        flavor_row.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(flavor_row, text="Flavor:", font=lf, bg=PANEL, fg=SUBTEXT, width=10, anchor="w").pack(side="left")

        self._flavor_var = tk.StringVar()
        self._flavor_combo = ttk.Combobox(
            flavor_row, textvariable=self._flavor_var,
            font=valf, state="readonly", width=28,
        )
        self._flavor_combo.pack(side="left", padx=(4, 0))
        self._flavor_combo.bind("<<ComboboxSelected>>", self._on_flavor_selected)

        # Dates (auto-computed, read-only display)
        today    = datetime.date.today()
        exp_date = today + datetime.timedelta(days=365)

        self._mfg_date = today
        self._exp_date = exp_date

        for label, val in [("Mfg Date:", today.strftime("%Y-%m-%d")), ("Exp Date:", exp_date.strftime("%Y-%m-%d"))]:
            row = tk.Frame(panel, bg=PANEL)
            row.pack(fill="x", padx=16, pady=2)
            tk.Label(row, text=label, font=lf, bg=PANEL, fg=SUBTEXT, width=10, anchor="w").pack(side="left")
            var = tk.StringVar(value=val)
            tk.Label(row, textvariable=var, font=valf, bg=PANEL, fg=SUBTEXT).pack(side="left", padx=4)
            if label.startswith("Mfg"):
                self._mfg_var = var
            else:
                self._exp_var = var

        # Quantity
        qty_row = tk.Frame(panel, bg=PANEL)
        qty_row.pack(fill="x", padx=16, pady=(8, 4))
        tk.Label(qty_row, text="Quantity:", font=lf, bg=PANEL, fg=SUBTEXT, width=10, anchor="w").pack(side="left")

        self._qty_var = tk.StringVar(value="1")
        qty_entry = tk.Entry(qty_row, textvariable=self._qty_var, font=valf, width=6, bg="#0D1117", fg=WHITE,
                             insertbackground=WHITE, relief="flat")
        qty_entry.pack(side="left", padx=4)

        # Print button
        self._print_btn = tk.Button(
            panel,
            text="PRINT & ENCODE",
            font=bigf,
            bg=GREEN, fg=WHITE,
            relief="flat", cursor="hand2",
            activebackground="#00a07f", activeforeground=WHITE,
            pady=10,
            command=self._on_print,
        )
        self._print_btn.pack(fill="x", padx=16, pady=12)

    def _build_log_panel(self, parent):
        panel = tk.Frame(parent, bg=PANEL)
        panel.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 0))

        hf   = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        logf = tkfont.Font(family="Consolas", size=9)

        tk.Label(panel, text="JOB LOG", font=hf, bg=PANEL, fg=SUBTEXT).pack(anchor="w", padx=16, pady=(12, 4))
        ttk.Separator(panel, orient="horizontal").pack(fill="x", padx=16)

        log_frame = tk.Frame(panel, bg="#0D1117")
        log_frame.pack(fill="both", expand=True, padx=16, pady=(4, 12))

        self._log_text = tk.Text(
            log_frame, font=logf, bg="#0D1117", fg=SUBTEXT,
            insertbackground=WHITE, relief="flat", state="disabled",
        )
        log_scroll = ttk.Scrollbar(log_frame, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self._log_text.pack(fill="both", expand=True, padx=4, pady=4)

        self._log_text.tag_configure("ok",   foreground=GREEN)
        self._log_text.tag_configure("err",  foreground=RED)
        self._log_text.tag_configure("info", foreground=SUBTEXT)
        self._log_text.tag_configure("head", foreground=YELLOW)

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=ACCENT, height=24)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self._status_var = tk.StringVar(value="Load a copacker config to begin.")
        sf = tkfont.Font(family="Segoe UI", size=8)
        tk.Label(bar, textvariable=self._status_var, font=sf, bg=ACCENT, fg=SUBTEXT, anchor="w").pack(side="left", padx=12)

    # ─── Config loading ───────────────────────────────────────

    def _load_config_dialog(self):
        available = cl.LocalJsonFlavorProvider.list_available()
        if not available:
            messagebox.showwarning("No configs found",
                                   "No copacker config files found in tag-encode/configs/.\n"
                                   "Place copacker_<ID>.json files there and restart.")
            return

        if len(available) == 1:
            self._load_config(available[0]["path"])
            return

        # Multiple configs — show picker dialog
        picker = tk.Toplevel(self)
        picker.title("Select Copacker Config")
        picker.configure(bg=BG)
        picker.geometry("400x260")
        picker.grab_set()

        bf = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        sf = tkfont.Font(family="Segoe UI", size=9)

        tk.Label(picker, text="Select your copacker:", font=bf, bg=BG, fg=WHITE).pack(pady=(20, 8))

        selected = tk.StringVar()
        for entry in available:
            label = f"{entry['copacker_name']}  ({entry['copacker_id']})"
            tk.Radiobutton(
                picker, text=label, variable=selected, value=entry["path"],
                font=sf, bg=BG, fg=WHITE, selectcolor=ACCENT,
                activebackground=BG, activeforeground=WHITE,
            ).pack(anchor="w", padx=40, pady=2)
        selected.set(available[0]["path"])

        def confirm():
            picker.destroy()
            self._load_config(selected.get())

        tk.Button(picker, text="Load", font=sf, bg=GREEN, fg=WHITE, relief="flat",
                  padx=20, pady=6, cursor="hand2",
                  activebackground="#00a07f", activeforeground=WHITE,
                  command=confirm).pack(pady=16)

    def _load_config(self, path: str):
        try:
            self._provider = cl.LocalJsonFlavorProvider(config_path=path)
            self._flavors  = self._provider.get_active_flavors()
            self._copacker_name_var.set(self._provider.get_copacker_name())
            self._copacker_id_var.set(f"ID: {self._provider.get_copacker_id()}")
            self._populate_flavor_dropdown()
            self._log(f"Loaded config: {self._provider.get_copacker_name()} ({self._provider.get_copacker_id()})", "head")
            self._log(f"{len(self._flavors)} flavor(s) available.", "info")
            self._set_status(f"Config loaded — {self._provider.get_copacker_name()}")
        except Exception as e:
            messagebox.showerror("Config load error", str(e))

    def _populate_flavor_dropdown(self):
        entries = []
        for f in self._flavors:
            num    = f["flavor_number"]
            name   = f["flavor_name"]
            status = f.get("status", "In Production")
            label  = f"{num} — {name}"
            if status != "In Production":
                label += f"  [{status}]"
            entries.append(label)
        self._flavor_combo["values"] = entries
        if entries:
            self._flavor_combo.current(0)
            self._on_flavor_selected()

    def _on_flavor_selected(self, _event=None):
        pass  # Future: preview fields on selection

    # ─── Printer check ────────────────────────────────────────

    def _check_printer(self):
        found = usb_mod.SatoPrinter.is_available()
        self._printer_dot.configure(fg=GREEN if found else RED)
        msg = "Printer found." if found else "Printer NOT found — check USB cable and close TagPrinter 2.3."
        self._set_status(msg)
        self._log(msg, "ok" if found else "err")

    # ─── Print job ────────────────────────────────────────────

    def _on_print(self):
        if self._printing:
            return
        if not self._provider:
            messagebox.showwarning("No config", "Load a copacker config first.")
            return

        idx = self._flavor_combo.current()
        if idx < 0 or idx >= len(self._flavors):
            messagebox.showwarning("No flavor", "Select a flavor.")
            return

        try:
            qty = int(self._qty_var.get())
            if qty < 1 or qty > 9999:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid quantity", "Enter a number between 1 and 9999.")
            return

        flavor = self._flavors[idx]
        self._run_print_job(flavor, qty)

    def _run_print_job(self, flavor: dict, qty: int):
        self._printing = True
        self._print_btn.configure(state="disabled", bg=DIM, text="Printing...")
        self._set_status("Building SBPL...")

        today    = datetime.date.today()
        exp_date = today + datetime.timedelta(days=365)

        try:
            sbpl_str = sbpl.build_sbpl(
                flavor_number = flavor["flavor_number"],
                flavor_name   = flavor["flavor_name"],
                gtin          = flavor.get("gtin", ""),
                mfg_date      = today,
                exp_date      = exp_date,
                copacker_id   = self._provider.get_copacker_id(),
                quantity       = qty,
            )
        except Exception as e:
            self._finish_print(success=False, msg=f"SBPL build error: {e}")
            return

        self._log(
            f"Job: flavor={flavor['flavor_number']} ({flavor['flavor_name']}), "
            f"qty={qty}, mfg={today}, exp={exp_date}, copacker={self._provider.get_copacker_id()}",
            "head",
        )

        printer = usb_mod.SatoPrinter()

        def worker():
            try:
                printer.print_sbpl(sbpl_str, on_status=lambda m: self.after(0, lambda: self._set_status(m)))
                self.after(0, lambda: self._finish_print(True, "Print job complete."))
            except usb_mod.PrinterNotFoundError as e:
                self.after(0, lambda: self._finish_print(False, str(e)))
            except Exception as e:
                self.after(0, lambda: self._finish_print(False, f"Print error: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_print(self, success: bool, msg: str):
        self._printing = False
        self._print_btn.configure(state="normal", bg=GREEN, text="PRINT & ENCODE")
        tag = "ok" if success else "err"
        self._log(msg, tag)
        self._set_status(msg)
        if not success:
            messagebox.showerror("Print failed", msg)

    # ─── Helpers ──────────────────────────────────────────────

    def _log(self, msg: str, tag: str = "info"):
        import time
        ts = time.strftime("%H:%M:%S")
        self._log_text.configure(state="normal")
        self._log_text.insert("end", f"{ts}  {msg}\n", tag)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _set_status(self, msg: str):
        self._status_var.set(msg)


if __name__ == "__main__":
    app = TagEncodeApp()
    app.mainloop()
