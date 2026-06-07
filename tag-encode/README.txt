tag-encode
==========
Printing and NFC encoding app for BIB labels.

Hardware
--------
- Printer    : SATO CL4NX Plus 203dpi (RFID/NFC module installed)
- NFC tags   : NTAG213 / NTAG215 / NTAG216 inlays (ISO/IEC 14443 TypeA)
- Connection : USB cable → Windows print spooler (win32print, RAW datatype)
- Verify reader: ACR122U or ACR1252U USB (same as tag-read)

Python dependency: pywin32  (pip install pywin32)

Printer communication
---------------------
Raw SBPL sent via win32print.WritePrinter() with RAW spool datatype.
Printer appears as a standard Windows device after SATO driver install.

SBPL command structure (ISO/IEC 14443 TypeA write)
----------------------------------------------------
<A>
<RK>1,0,<dataSpec>,<data>,ict:03,lma:0,prt:0,fsw:0
[visual label commands — barcode, text, etc.]
<Q>{quantity}
<Z>

  ict:03 = ISO14443 TypeA / NTAG family
  lma:0  = no memory lock
  prt:0  = no password protection
  fsw:0  = normal feed after encode

Exact dataSpec and data format confirmed from captured SBPL job in next session.

Fields encoded per tag
----------------------
  flavor_number  : 3-digit integer, last 3 digits of P/N 740-XXXX
                   e.g. Lemon Lime = P/N 740-0145 → flavor_number = 145
  mfg_date       : date of print job (YYYY-MM-DD)
  exp_date       : mfg_date + 365 days
  copacker_id    : one of "101122IL", "102089TX", "102029UK"
  validity       : "valid"

NOT encoded: flavor name, GTIN, vendor_item, label REV

UID is the chip's hardware UID — not pre-written, read back after print
via DC2+PJ / ESC+RU for encode-verify.

Copacker config files  (configs/copacker_<ID>.json)
----------------------------------------------------
One JSON file per copacker installation, loaded at app startup.
The flavor dropdown is populated from this file's "flavors" array,
showing only flavors where this copacker has a vendor_item assigned.

Dropdown display format: "145 — Lemon Lime"

Copacker IDs and names:
  101122IL  →  Tone Products (TP)       — Illinois
  102089TX  →  Sunny Sky Products (SSP) — Texas
  102029UK  →  Simpsons Beverages (SB)  — UK

Config schema:
{
  "copacker_id":   "101122IL",
  "copacker_name": "Tone Products",
  "short_name":    "TP",
  "location":      "IL",
  "flavors": [
    {
      "flavor_number": 115,
      "flavor_name":   "Electrolytes",
      "gtin":          "00850010449128",
      "vendor_item":   "35ELCBEV",
      "status":        "In Production"
    },
    ...
  ]
}

Flavor counts per copacker:
  101122IL (TP)  : 19 flavors (18 In Production, 1 In Design)
  102089TX (SSP) : 21 flavors (all In Production)
  102029UK (SB)  :  8 flavors (all In Production)

Master flavor lookup: shared/flavors.json
  Maps flavor_number → { flavor_name, gtin, status }
  Used by tag-read and tag-verify for display-only name resolution.

To do in next session
---------------------
1. Provide one captured SBPL job string from existing app
   (enable SATO print-to-file, or copy raw string from existing code)
2. Build tag-encode GUI + SBPL generator + USB send + encode-verify loop
