"""
Parser for NFC tag user memory.
Tries NDEF → delimited text → raw hex fallback.

Expected BIB label fields:
  uid, mfg_date, exp_date, flavor_number, copacker_id, validity

Flavor name is resolved from shared/flavors.json when available.
"""

import json
import os
import re
import struct

# Load master flavor lookup once at import time
_FLAVORS: dict = {}
_FLAVORS_PATH = os.path.join(os.path.dirname(__file__), "flavors.json")
try:
    with open(_FLAVORS_PATH) as _f:
        _FLAVORS = {int(k): v for k, v in json.load(_f).items()}
except Exception:
    pass


def lookup_flavor_name(flavor_number) -> str | None:
    """Return flavor name for a numeric flavor number, or None if unknown."""
    try:
        return _FLAVORS.get(int(flavor_number), {}).get("flavor_name")
    except (TypeError, ValueError):
        return None


FIELD_ALIASES = {
    "uid":          ["uid", "uuid", "id"],
    "mfg_date":     ["mfg", "mfg_date", "mfgdate", "manufactured", "manufacture_date", "prod_date"],
    "exp_date":     ["exp", "exp_date", "expdate", "expiration", "expires", "best_by", "bestby"],
    "flavor_number":["flavor", "flavor_number", "flavorno", "flavor_no", "flavornum", "fno"],
    "copacker_id":  ["copacker", "copacker_id", "copacker_id", "co_packer", "copacker_id", "coid"],
    "validity":     ["valid", "validity", "status", "ok", "active"],
}


class ParsedTag:
    __slots__ = [
        "uid", "uid_fmt", "tag_type",
        "mfg_date", "exp_date", "flavor_number", "flavor_name",
        "copacker_id", "validity",
        "raw_text", "ndef_records", "parse_method", "raw_hex",
        "unknown_fields",
    ]

    def __init__(self):
        for s in self.__slots__:
            setattr(self, s, None)
        self.ndef_records = []
        self.unknown_fields = {}

    def to_dict(self):
        return {s: getattr(self, s) for s in self.__slots__}


def parse(tag_dict):
    pt = ParsedTag()
    pt.uid = tag_dict.get("uid_hex", "")
    pt.uid_fmt = tag_dict.get("uid_fmt", "")
    pt.tag_type = tag_dict.get("tag_type", "")

    user_mem = tag_dict.get("user_memory", b"")
    pt.raw_hex = user_mem.hex().upper() if user_mem else ""

    # Try NDEF
    records = _parse_ndef_tlv(user_mem)
    if records:
        pt.ndef_records = records
        pt.parse_method = "NDEF"
        for rec in records:
            text = rec.get("text", "")
            if text:
                _extract_fields(pt, text)
                break
    else:
        # Try raw UTF-8 text
        try:
            text = user_mem.rstrip(b"\x00\xfe").decode("utf-8").strip()
            if text and any(c.isprintable() for c in text):
                pt.raw_text = text
                pt.parse_method = "RAW_TEXT"
                _extract_fields(pt, text)
        except Exception:
            pt.parse_method = "RAW_HEX"

    # Resolve flavor name from master lookup
    if pt.flavor_number is not None:
        pt.flavor_name = lookup_flavor_name(pt.flavor_number)

    return pt


# ──────────────────────────────────────────────────────────────
# Field extraction — supports JSON, key=value/key:value, pipe-delimited
# ──────────────────────────────────────────────────────────────

def _extract_fields(pt, text):
    pt.raw_text = text

    # JSON
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            _apply_dict(pt, {k.lower(): str(v) for k, v in obj.items()})
            return
    except Exception:
        pass

    # key=value or key:value (one per line or separated by | , ;)
    pairs = re.findall(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*[=:]\s*([^|,;\n\r]+)", text)
    if pairs:
        _apply_dict(pt, {k.lower().strip(): v.strip() for k, v in pairs})
        return

    # Pipe-delimited positional: mfg|exp|flavor|copacker|valid  (UID comes from NFC layer)
    parts = [p.strip() for p in text.split("|")]
    if len(parts) >= 2:
        fields = ["mfg_date", "exp_date", "flavor_number", "copacker_id", "validity"]
        for i, field in enumerate(fields):
            if i < len(parts) and parts[i]:
                setattr(pt, field, parts[i])
        return

    # Comma-delimited positional — same field order
    parts = [p.strip() for p in text.split(",")]
    if len(parts) >= 2:
        fields = ["mfg_date", "exp_date", "flavor_number", "copacker_id", "validity"]
        for i, field in enumerate(fields):
            if i < len(parts) and parts[i]:
                setattr(pt, field, parts[i])


def _apply_dict(pt, d):
    for canonical, aliases in FIELD_ALIASES.items():
        if canonical == "uid":
            continue  # UID comes from NFC hardware
        for alias in aliases:
            if alias in d:
                setattr(pt, canonical, d.pop(alias))
                break
    pt.unknown_fields = d


# ──────────────────────────────────────────────────────────────
# NDEF TLV / NDEF Message parsers (minimal, covers well-known types)
# ──────────────────────────────────────────────────────────────

def _parse_ndef_tlv(data):
    records = []
    i = 0
    while i < len(data):
        t = data[i]; i += 1
        if t == 0x00:
            continue
        if t == 0xFE:
            break
        if i >= len(data):
            break
        length = data[i]; i += 1
        if length == 0xFF:
            if i + 2 > len(data):
                break
            length = struct.unpack(">H", data[i:i+2])[0]; i += 2
        if i + length > len(data):
            break
        payload = data[i:i+length]; i += length
        if t == 0x03:  # NDEF Message TLV
            records.extend(_parse_ndef_message(payload))
    return records


def _parse_ndef_message(data):
    records = []
    i = 0
    while i < len(data):
        if i >= len(data):
            break
        flags = data[i]; i += 1
        tnf = flags & 0x07
        sr = bool(flags & 0x10)
        il = bool(flags & 0x08)

        if i >= len(data): break
        type_len = data[i]; i += 1

        if sr:
            if i >= len(data): break
            payload_len = data[i]; i += 1
        else:
            if i + 4 > len(data): break
            payload_len = struct.unpack(">I", bytes(data[i:i+4]))[0]; i += 4

        id_len = 0
        if il:
            if i >= len(data): break
            id_len = data[i]; i += 1

        if i + type_len > len(data): break
        rec_type = bytes(data[i:i+type_len]).decode("ascii", errors="replace"); i += type_len
        i += id_len  # skip ID

        if i + payload_len > len(data): break
        payload = bytes(data[i:i+payload_len]); i += payload_len

        records.append({
            "tnf": tnf,
            "type": rec_type,
            "payload": payload,
            "text": _decode_ndef_payload(tnf, rec_type, payload),
        })

        if flags & 0x40:  # ME = Message End
            break
    return records


def _decode_ndef_payload(tnf, rec_type, payload):
    if tnf == 0x01 and rec_type == "T":  # Well-Known Text
        if not payload:
            return ""
        lang_len = payload[0] & 0x3F
        is_utf16 = bool(payload[0] & 0x80)
        text_bytes = payload[1 + lang_len:]
        enc = "utf-16" if is_utf16 else "utf-8"
        return text_bytes.decode(enc, errors="replace")

    if tnf == 0x01 and rec_type == "U":  # Well-Known URI
        prefixes = {
            0x00: "", 0x01: "http://www.", 0x02: "https://www.",
            0x03: "http://", 0x04: "https://", 0x05: "tel:", 0x06: "mailto:",
        }
        if payload:
            return prefixes.get(payload[0], "") + payload[1:].decode("utf-8", errors="replace")

    try:
        return payload.decode("utf-8", errors="replace")
    except Exception:
        return payload.hex().upper()
