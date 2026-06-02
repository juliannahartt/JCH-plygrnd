"""
tag-verify — BIB Label 100% NFC Verification Station
Runs on Windows tablets (Surface) at production line start/end.
Large touch-friendly UI. Pass = green, Fail = red, full-screen alert.
"""

import sys
import os
import time
import tkinter as tk
from tkinter import ttk, font as tkfont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import nfc_reader as nfc
import tag_parser as parser

# ─── Colors ───────────────────────────────────────────────────
BG_IDLE   = "#1A1A2E"
BG_PASS   = "#00B894"
BG_FAIL   = "#D63031"
BG_PANEL  = "#16213E"
ACCENT    = "#0F3460"
WHITE     = "#FFFFFF"
GRAY      = "#636E72"
SUBTEXT   = "#B2BEC3"

VERIFY_FIELDS = ["mfg_date", "exp_date", "flavor_number", "copacker_id", "validity"]
FIELD_LABELS  = {
    "uid_fmt":       "Tag UID",
    "tag_type":      "Tag Type",
    "mfg_date":      "Mfg Date",
    "exp_date":      "Expiration",
    "flavor_number": "Flavor #",
    "copacker_id":   "Copacker",
    "validity":      "Valid",
}

# A tag is considered "valid" if the validity field contains one of these values
VALID_VALUES = {"true", "yes", "1", "valid", "ok", "active", "pass"}

# How long (ms) to hold the PASS/FAIL state before returning to idle
HOLD_MS = 3000


class TagVerifyApp(tk.Tk):
    MAX_LOG = 200

    def __init__(self):
        super().__init__()
        self.title("tag-verify  |  BIB Production Line Scanner")
        self.configure(bg=BG_IDLE)
        self.geometry("1024x768")
        self.attributes("-fullscreen", False)  # Set True for production tablet deployment

        self._scanner = None
        self._last_uid = None
        self._pass_count = 0
        self._fail_count = 0
        self._log = []

        self._build_ui()
        self.after(300, self._start_scanner)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<F11>", lambda _: self._toggle_fullscreen())
        self.bind("<Escape>", lambda _: self.attributes("-fullscreen", False))

    # ─── UI ───────────────────────────────────────────────────

    def _build_ui(self):
        # Top bar
        top = tk.Frame(self, bg=ACCENT, height=64)
        top.pack(fill="x")
        top.pack_propagate(False)

        title_font = tkfont.Font(family="Segoe UI", size=20, weight="bold")
        sub_font   = tkfont.Font(family="Segoe UI", size=11)

        tk.Label(top, text="tag-verify", font=title_font, bg=ACCENT, fg=WHITE).pack(side="left", padx=24, pady=8)
        tk.Label(top, text="Production Line NFC Verification", font=sub_font, bg=ACCENT, fg=SUBTEXT).pack(side="left", pady=8)

        self._status_label = tk.Label(top, text="●  Connecting...", font=sub_font, bg=ACCENT, fg=GRAY)
        self._status_label.pack(side="right", padx=24)

        # Main result area
        self._result_frame = tk.Frame(self, bg=BG_IDLE)
        self._result_frame.pack(fill="both", expand=True)

        result_font = tkfont.Font(family="Segoe UI", size=64, weight="bold")
        uid_font    = tkfont.Font(family="Consolas", size=16)
        detail_font = tkfont.Font(family="Segoe UI", size=14)

        self._big_label = tk.Label(
            self._result_frame, text="SCAN TAG",
            font=result_font, bg=BG_IDLE, fg=SUBTEXT,
        )
        self._big_label.pack(pady=(60, 8))

        self._uid_label = tk.Label(
            self._result_frame, text="",
            font=uid_font, bg=BG_IDLE, fg=WHITE,
        )
        self._uid_label.pack()

        # Field summary grid
        self._field_frame = tk.Frame(self._result_frame, bg=BG_IDLE)
        self._field_frame.pack(pady=16)

        self._field_vars = {}
        lbl_font = tkfont.Font(family="Segoe UI", size=13)
        val_font = tkfont.Font(family="Consolas", size=15, weight="bold")

        for i, key in enumerate(["mfg_date", "exp_date", "flavor_number", "copacker_id", "validity"]):
            label = FIELD_LABELS[key]
            row = tk.Frame(self._field_frame, bg=BG_IDLE)
            row.grid(row=i // 2, column=i % 2, padx=40, pady=6, sticky="w")
            tk.Label(row, text=f"{label}:", font=lbl_font, bg=BG_IDLE, fg=SUBTEXT, width=14, anchor="e").pack(side="left")
            var = tk.StringVar(value="—")
            self._field_vars[key] = var
            tk.Label(row, textvariable=var, font=val_font, bg=BG_IDLE, fg=WHITE, anchor="w").pack(side="left", padx=8)

        # Bottom stats + log
        bottom = tk.Frame(self, bg=BG_PANEL, height=180)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)

        stats_font  = tkfont.Font(family="Segoe UI", size=28, weight="bold")
        slabel_font = tkfont.Font(family="Segoe UI", size=10)
        log_font    = tkfont.Font(family="Consolas", size=9)

        stats = tk.Frame(bottom, bg=BG_PANEL)
        stats.pack(side="left", padx=32, pady=12)

        self._pass_var = tk.StringVar(value="0")
        self._fail_var = tk.StringVar(value="0")

        for var, label, color in [
            (self._pass_var, "PASS", BG_PASS),
            (self._fail_var, "FAIL", BG_FAIL),
        ]:
            col = tk.Frame(stats, bg=BG_PANEL)
            col.pack(side="left", padx=24)
            tk.Label(col, textvariable=var, font=stats_font, bg=BG_PANEL, fg=color).pack()
            tk.Label(col, text=label, font=slabel_font, bg=BG_PANEL, fg=SUBTEXT).pack()

        # Reset button
        tk.Button(
            stats, text="Reset Counts",
            font=slabel_font, bg=ACCENT, fg=WHITE, relief="flat",
            activebackground=BG_PANEL, activeforeground=WHITE,
            padx=12, pady=6, cursor="hand2",
            command=self._reset_counts,
        ).pack(side="left", padx=32, pady=32)

        # Log
        log_frame = tk.Frame(bottom, bg=BG_PANEL)
        log_frame.pack(fill="both", expand=True, side="right", padx=16, pady=8)

        self._log_box = tk.Listbox(
            log_frame, font=log_font, bg="#0D1117", fg=SUBTEXT,
            selectbackground=ACCENT, relief="flat", bd=0, activestyle="none",
        )
        log_scroll = ttk.Scrollbar(log_frame, command=self._log_box.yview)
        self._log_box.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self._log_box.pack(fill="both", expand=True)

        # Status bar
        bar = tk.Frame(self, bg=ACCENT, height=28)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self._bottom_status = tk.StringVar(value="")
        tk.Label(bar, textvariable=self._bottom_status, font=tkfont.Font(family="Segoe UI", size=9),
                 bg=ACCENT, fg=SUBTEXT, anchor="w").pack(side="left", padx=12)
        tk.Label(bar, text="F11 = fullscreen  |  Esc = exit fullscreen",
                 font=tkfont.Font(family="Segoe UI", size=9), bg=ACCENT, fg=GRAY).pack(side="right", padx=12)

    # ─── Scanner ──────────────────────────────────────────────

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

    def _on_tag(self, tag_dict):
        self.after(0, lambda: self._handle_tag(tag_dict))

    def _on_status(self, msg):
        self.after(0, lambda: self._update_status(msg))

    # ─── Verify logic ─────────────────────────────────────────

    def _handle_tag(self, tag_dict):
        uid = tag_dict.get("uid_hex", "")
        if uid == self._last_uid:
            return
        self._last_uid = uid

        pt = parser.parse(tag_dict)
        passed = self._is_valid(pt)

        # Update field grid
        for key, var in self._field_vars.items():
            v = getattr(pt, key, None) or "—"
            var.set(str(v))

        if passed:
            self._pass_count += 1
            self._pass_var.set(str(self._pass_count))
            self._show_result("PASS", BG_PASS, tag_dict.get("uid_fmt", uid))
        else:
            self._fail_count += 1
            self._fail_var.set(str(self._fail_count))
            self._show_result("FAIL", BG_FAIL, tag_dict.get("uid_fmt", uid))

        self._add_log(pt, passed)
        self.after(HOLD_MS, self._return_to_idle)

    def _is_valid(self, pt):
        """
        A tag passes verification if all required fields are present
        and the validity field (if present) is affirmative.
        """
        required = ["mfg_date", "exp_date", "flavor_number", "copacker_id"]
        for f in required:
            if not getattr(pt, f, None):
                return False
        validity = getattr(pt, "validity", None)
        if validity is not None:
            return validity.strip().lower() in VALID_VALUES
        # If no validity field encoded, pass as long as required fields present
        return True

    def _show_result(self, text, bg, uid):
        self._result_frame.configure(bg=bg)
        self._big_label.configure(text=text, bg=bg, fg=WHITE)
        self._uid_label.configure(text=uid, bg=bg)
        self._field_frame.configure(bg=bg)
        for widget in self._field_frame.winfo_children():
            for child in widget.winfo_children():
                try:
                    child.configure(bg=bg)
                except Exception:
                    pass

    def _return_to_idle(self):
        self._last_uid = None
        self._result_frame.configure(bg=BG_IDLE)
        self._big_label.configure(text="SCAN TAG", bg=BG_IDLE, fg=SUBTEXT)
        self._uid_label.configure(text="", bg=BG_IDLE)
        self._field_frame.configure(bg=BG_IDLE)
        for key, var in self._field_vars.items():
            var.set("—")
        for widget in self._field_frame.winfo_children():
            for child in widget.winfo_children():
                try:
                    child.configure(bg=BG_IDLE)
                except Exception:
                    pass

    def _add_log(self, pt, passed):
        ts = time.strftime("%H:%M:%S")
        result = "PASS" if passed else "FAIL"
        uid = pt.uid_fmt or pt.uid or "?"
        flavor = pt.flavor_number or "?"
        copacker = pt.copacker_id or "?"
        entry = f"{ts}  {result}  {uid}  flavor={flavor}  copacker={copacker}"
        self._log.insert(0, entry)
        if len(self._log) > self.MAX_LOG:
            self._log.pop()
        self._log_box.insert(0, entry)
        if self._log_box.size() > self.MAX_LOG:
            self._log_box.delete(self.MAX_LOG, "end")
        # Color-code log entries
        color = BG_PASS if passed else BG_FAIL
        self._log_box.itemconfigure(0, fg=color)

    def _reset_counts(self):
        self._pass_count = 0
        self._fail_count = 0
        self._pass_var.set("0")
        self._fail_var.set("0")
        self._log.clear()
        self._log_box.delete(0, "end")

    def _update_status(self, msg):
        self._status_label.configure(text=f"●  {msg}")
        self._bottom_status.set(msg)

    def _toggle_fullscreen(self):
        current = self.attributes("-fullscreen")
        self.attributes("-fullscreen", not current)


if __name__ == "__main__":
    app = TagVerifyApp()
    app.mainloop()
