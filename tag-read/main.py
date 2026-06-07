"""
tag-read — BIB Label NFC Tag Reader
Reads NTAG21x via ACR122U USB reader (Windows / PC/SC).
"""

import sys
import os
import time
import tkinter as tk
from tkinter import ttk, font as tkfont

# Allow importing shared modules from parent directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import nfc_reader as nfc
import tag_parser as parser

# ─── Color palette ────────────────────────────────────────────
BG       = "#1A1A2E"
PANEL    = "#16213E"
ACCENT   = "#0F3460"
GREEN    = "#00B894"
RED      = "#D63031"
YELLOW   = "#FDCB6E"
WHITE    = "#FFFFFF"
GRAY     = "#636E72"
SUBTEXT  = "#B2BEC3"

FIELD_LABELS = {
    "uid_fmt":       "Tag UID",
    "tag_type":      "Tag Type",
    "mfg_date":      "Mfg Date",
    "exp_date":      "Expiration Date",
    "flavor_number": "Flavor #",
    "flavor_name":   "Flavor Name",
    "copacker_id":   "Copacker ID",
    "validity":      "Validity",
}

FIELD_ORDER = ["uid_fmt", "tag_type", "mfg_date", "exp_date", "flavor_number", "flavor_name", "copacker_id", "validity"]


class TagReadApp(tk.Tk):
    MAX_LOG = 50

    def __init__(self):
        super().__init__()
        self.title("tag-read  |  BIB NFC Reader")
        self.configure(bg=BG)
        self.geometry("860x720")
        self.minsize(700, 580)
        self.resizable(True, True)

        self._field_vars = {}
        self._scan_history = []
        self._scanner = None
        self._last_uid = None

        self._build_ui()
        self.after(200, self._start_scanner)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─── UI construction ──────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)

        self._build_fields_panel(main)
        self._build_right_panel(main)
        self._build_statusbar()

    def _build_header(self):
        hdr = tk.Frame(self, bg=ACCENT, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        title_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        sub_font   = tkfont.Font(family="Segoe UI", size=9)

        tk.Label(hdr, text="tag-read", font=title_font, bg=ACCENT, fg=WHITE).pack(side="left", padx=20, pady=6)
        tk.Label(hdr, text="BIB NFC Label Scanner", font=sub_font, bg=ACCENT, fg=SUBTEXT).pack(side="left", pady=6)

        self._status_dot = tk.Label(hdr, text="●", font=tkfont.Font(size=14), bg=ACCENT, fg=GRAY)
        self._status_dot.pack(side="right", padx=20)

    def _build_fields_panel(self, parent):
        outer = tk.Frame(parent, bg=PANEL, bd=0)
        outer.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=8)

        header_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        label_font  = tkfont.Font(family="Segoe UI", size=9)
        value_font  = tkfont.Font(family="Consolas", size=13, weight="bold")

        tk.Label(outer, text="TAG FIELDS", font=header_font, bg=PANEL, fg=SUBTEXT).pack(anchor="w", padx=16, pady=(12, 6))
        ttk.Separator(outer, orient="horizontal").pack(fill="x", padx=16)

        for key in FIELD_ORDER:
            row = tk.Frame(outer, bg=PANEL)
            row.pack(fill="x", padx=16, pady=6)

            label = FIELD_LABELS.get(key, key)
            tk.Label(row, text=label, font=label_font, bg=PANEL, fg=SUBTEXT, width=18, anchor="w").pack(side="left")

            var = tk.StringVar(value="—")
            self._field_vars[key] = var

            val_lbl = tk.Label(row, textvariable=var, font=value_font, bg=PANEL, fg=WHITE, anchor="w", wraplength=340)
            val_lbl.pack(side="left", fill="x", expand=True)
            setattr(self, f"_lbl_{key}", val_lbl)

        # Raw / NDEF section
        ttk.Separator(outer, orient="horizontal").pack(fill="x", padx=16, pady=(8, 0))
        tk.Label(outer, text="RAW MEMORY (hex)", font=header_font, bg=PANEL, fg=SUBTEXT).pack(anchor="w", padx=16, pady=(8, 4))

        raw_frame = tk.Frame(outer, bg="#0D1117")
        raw_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        self._raw_text = tk.Text(
            raw_frame,
            font=tkfont.Font(family="Consolas", size=9),
            bg="#0D1117", fg=GREEN, insertbackground=WHITE,
            relief="flat", wrap="word", state="disabled",
            height=6,
        )
        raw_scroll = ttk.Scrollbar(raw_frame, command=self._raw_text.yview)
        self._raw_text.configure(yscrollcommand=raw_scroll.set)
        raw_scroll.pack(side="right", fill="y")
        self._raw_text.pack(fill="both", expand=True, padx=4, pady=4)

        # Parse method badge
        self._parse_method_var = tk.StringVar(value="")
        tk.Label(outer, textvariable=self._parse_method_var, font=label_font, bg=PANEL, fg=YELLOW).pack(anchor="w", padx=16, pady=(0, 8))

    def _build_right_panel(self, parent):
        right = tk.Frame(parent, bg=PANEL)
        right.grid(row=0, column=1, sticky="nsew", pady=8)

        header_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        log_font    = tkfont.Font(family="Consolas", size=8)

        tk.Label(right, text="SCAN LOG", font=header_font, bg=PANEL, fg=SUBTEXT).pack(anchor="w", padx=12, pady=(12, 6))
        ttk.Separator(right, orient="horizontal").pack(fill="x", padx=12)

        self._log_box = tk.Listbox(
            right,
            font=log_font,
            bg="#0D1117", fg=SUBTEXT,
            selectbackground=ACCENT, selectforeground=WHITE,
            relief="flat", bd=0, activestyle="none",
        )
        log_scroll = ttk.Scrollbar(right, command=self._log_box.yview)
        self._log_box.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y", pady=(4, 12))
        self._log_box.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        # Clear button
        tk.Button(
            right, text="Clear Log",
            font=tkfont.Font(family="Segoe UI", size=9),
            bg=ACCENT, fg=WHITE, relief="flat", cursor="hand2",
            activebackground=PANEL, activeforeground=WHITE,
            command=self._clear_log,
            padx=8, pady=4,
        ).pack(anchor="e", padx=12, pady=(0, 8))

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=ACCENT, height=24)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self._status_var = tk.StringVar(value="Initializing...")
        status_font = tkfont.Font(family="Segoe UI", size=8)
        tk.Label(bar, textvariable=self._status_var, font=status_font, bg=ACCENT, fg=SUBTEXT, anchor="w").pack(side="left", padx=12)

        self._scan_count_var = tk.StringVar(value="Scans: 0")
        tk.Label(bar, textvariable=self._scan_count_var, font=status_font, bg=ACCENT, fg=SUBTEXT, anchor="e").pack(side="right", padx=12)

    # ─── Scanner lifecycle ────────────────────────────────────

    def _start_scanner(self):
        self._scanner = nfc.ContinuousScanner(
            on_tag=self._on_tag,
            on_status=self._on_status,
        )
        self._scanner.start()

    def _on_close(self):
        if self._scanner:
            self._scanner.stop()
        self.destroy()

    # ─── Callbacks (called from background thread — use after()) ──

    def _on_tag(self, tag_dict):
        self.after(0, lambda: self._handle_tag(tag_dict))

    def _on_status(self, msg):
        self.after(0, lambda: self._update_status(msg))

    # ─── Tag handling ─────────────────────────────────────────

    def _handle_tag(self, tag_dict):
        uid = tag_dict.get("uid_hex", "")
        if uid == self._last_uid:
            return  # Debounce duplicate reads of same tag
        self._last_uid = uid

        pt = parser.parse(tag_dict)

        self._update_fields(tag_dict, pt)
        self._add_log_entry(pt)

        count = len(self._scan_history)
        self._scan_count_var.set(f"Scans: {count}")
        self._status_dot.configure(fg=GREEN)
        self.after(2000, lambda: self._status_dot.configure(fg=GRAY))

    def _update_fields(self, tag_dict, pt):
        for key in FIELD_ORDER:
            if key == "uid_fmt":
                val = tag_dict.get("uid_fmt") or "—"
            elif key == "tag_type":
                val = tag_dict.get("tag_type") or "—"
            elif key == "flavor_name":
                val = pt.flavor_name or "—"
            else:
                val = getattr(pt, key, None) or "—"

            self._field_vars[key].set(val)
            lbl = getattr(self, f"_lbl_{key}", None)
            if lbl:
                lbl.configure(fg=self._value_color(key, val))

        # Raw hex with grouping
        raw = pt.raw_hex or ""
        grouped = " ".join(raw[i:i+2] for i in range(0, len(raw), 2))
        # Insert newlines every 48 hex chars (16 bytes)
        lines = [grouped[i:i+48] for i in range(0, len(grouped), 48)]
        formatted = "\n".join(lines)

        self._raw_text.configure(state="normal")
        self._raw_text.delete("1.0", "end")
        self._raw_text.insert("end", formatted if formatted else "(no data)")
        self._raw_text.configure(state="disabled")

        if pt.parse_method:
            self._parse_method_var.set(f"Parse method: {pt.parse_method}"
                                       + (f"  |  {len(pt.ndef_records)} NDEF record(s)" if pt.ndef_records else ""))
        else:
            self._parse_method_var.set("")

    def _value_color(self, key, val):
        if val == "—":
            return GRAY
        if key == "validity":
            v = val.lower()
            if v in ("true", "yes", "1", "valid", "ok", "active"):
                return GREEN
            if v in ("false", "no", "0", "invalid", "expired"):
                return RED
        return WHITE

    def _add_log_entry(self, pt):
        ts = time.strftime("%H:%M:%S")
        uid = pt.uid_fmt or pt.uid or "?"
        flavor = pt.flavor_number or "?"
        entry = f"{ts}  {uid}  flavor={flavor}"
        self._scan_history.insert(0, entry)
        if len(self._scan_history) > self.MAX_LOG:
            self._scan_history.pop()

        self._log_box.insert(0, entry)
        if self._log_box.size() > self.MAX_LOG:
            self._log_box.delete(self.MAX_LOG, "end")

    def _clear_log(self):
        self._scan_history.clear()
        self._log_box.delete(0, "end")
        self._scan_count_var.set("Scans: 0")
        self._last_uid = None

    def _update_status(self, msg):
        self._status_var.set(msg)
        if "error" in msg.lower() or "no reader" in msg.lower():
            self._status_dot.configure(fg=RED)
        elif "waiting" in msg.lower():
            self._status_dot.configure(fg=YELLOW)


if __name__ == "__main__":
    app = TagReadApp()
    app.mainloop()
