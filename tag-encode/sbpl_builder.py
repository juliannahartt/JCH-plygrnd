"""
SBPL command builder for SATO CL4NX Plus NFC label printing.

NFC data format (pipe-delimited, written to NTAG user memory):
  {flavor_number}|{mfg_date}|{exp_date}|{copacker_id}|valid
  e.g.: 145|2026-06-07|2027-06-07|102089TX|valid

IMPORTANT — confirm NFC_DATA_SPEC and RK_OPTIONS from captured TagPrinter 2.3
SBPL job before production use. The values below are best-estimate from
SATO programming reference (ict:03 = ISO14443 TypeA / NTAG family).

Label visual layout comes from configs/label_template.sbpl.
Paste the captured TagPrinter 2.3 SBPL into that file, replacing hard-coded
field values with the {variable} placeholders listed at the top of the file.
"""

import datetime
import os
import re


# ── NFC encode settings ───────────────────────────────────────
# CONFIRM these from a captured TagPrinter 2.3 SBPL job
NFC_DATA_SPEC  = "A"    # A = ASCII text. Change if captured job uses H (hex) or D (decimal)
NFC_RK_MODE   = "1"    # 1 = write user data
NFC_RK_BLOCK  = "0"    # Starting block (0 = first user memory page on NTAG)
NFC_IC_TYPE   = "03"   # ict:03 = ISO14443 TypeA / NTAG family
NFC_LOCK_MEM  = "0"    # lma:0 = no memory lock
NFC_PROTECT   = "0"    # prt:0 = no password protection
NFC_FEED_SW   = "0"    # fsw:0 = normal feed after encode

DATE_FMT = "%Y-%m-%d"  # YYYY-MM-DD — change if existing app uses a different format


# ── Template ──────────────────────────────────────────────────

_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "configs", "label_template.sbpl")


def load_template() -> str:
    with open(_TEMPLATE_PATH) as f:
        lines = f.readlines()
    # Strip comment lines (lines starting with #) before returning
    return "".join(l for l in lines if not l.lstrip().startswith("#"))


# ── Data assembly ─────────────────────────────────────────────

def format_nfc_data(flavor_number: int, mfg_date: datetime.date,
                    exp_date: datetime.date, copacker_id: str) -> str:
    return (
        f"{flavor_number}"
        f"|{mfg_date.strftime(DATE_FMT)}"
        f"|{exp_date.strftime(DATE_FMT)}"
        f"|{copacker_id}"
        f"|valid"
    )


def build_rk_command(nfc_data: str) -> str:
    length = len(nfc_data)
    return (
        f"<RK>{NFC_RK_MODE},{NFC_RK_BLOCK},{NFC_DATA_SPEC}{length:02d},{nfc_data},"
        f"ict:{NFC_IC_TYPE},lma:{NFC_LOCK_MEM},prt:{NFC_PROTECT},fsw:{NFC_FEED_SW}"
    )


def build_sbpl(
    flavor_number: int,
    flavor_name: str,
    gtin: str,
    mfg_date: datetime.date,
    exp_date: datetime.date,
    copacker_id: str,
    quantity: int,
    template: str | None = None,
) -> str:
    if template is None:
        template = load_template()

    nfc_data    = format_nfc_data(flavor_number, mfg_date, exp_date, copacker_id)
    rk_command  = build_rk_command(nfc_data)

    return template.format(
        rk_command    = rk_command,
        flavor_number = flavor_number,
        flavor_name   = flavor_name,
        gtin          = gtin,
        mfg_date      = mfg_date.strftime(DATE_FMT),
        exp_date      = exp_date.strftime(DATE_FMT),
        copacker_id   = copacker_id,
        quantity      = quantity,
        nfc_data      = nfc_data,
    )
