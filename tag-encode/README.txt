tag-encode
==========
Printing and NFC encoding app for BIB labels.

Hardware
--------
- Printer : SATO CL4NX Plus 203dpi (RFID/NFC module installed)
- NFC tags : NTAG213 / NTAG215 / NTAG216 inlays (ISO/IEC 14443 TypeA)
- Connection: USB cable → Windows print spooler (win32print, RAW datatype)
- Verify reader: ACR122U or ACR1252U USB (same as tag-read)

Printer communication
---------------------
Raw SBPL sent via win32print.WritePrinter() with RAW spool datatype.
No TCP/IP; printer appears as a standard Windows device after SATO driver install.

Python dependency: pywin32  (pip install pywin32)

SBPL command structure (ISO/IEC 14443 TypeA write)
----------------------------------------------------
<A>
<RK>1,0,<dataSpec>,<data>,ict:03,lma:0,prt:0,fsw:0
[visual label commands — barcode, text, etc.]
<Q>{quantity}
<Z>

Key parameters:
  ict:03   = IC type — ISO14443 TypeA / NTAG family
  lma:0    = no lock
  prt:0    = no password protection
  fsw:0    = normal feed after encode

Exact dataSpec and data format (raw hex vs. ASCII, NDEF wrapping) to be
confirmed from a captured SBPL job string in the next session.

Fields to encode per tag
------------------------
  mfg_date      : today's date (at print time)
  exp_date      : mfg_date + 365 days
  flavor_number : selected from copacker JSON flavor list
  copacker_id   : loaded from copacker JSON config
  validity      : "valid"

(UID is not pre-written — it is the chip's factory UID, read back after print
 via DC2+PJ / ESC+RU for verification.)

Copacker JSON config (structure TBD — bring example in next session)
---------------------------------------------------------------------
{
  "copacker_id": "ACME01",
  "flavors": [
    {"id": "F01", "name": "Cherry"},
    {"id": "F02", "name": "Lemon"}
  ]
}

One JSON file per copacker installation. Loaded at app startup.
Flavor dropdown is filtered from this list.

To do in next session
---------------------
1. Provide one captured SBPL job string from existing app
   (enable SATO print-to-file, or copy raw string from existing code)
2. Provide actual copacker JSON file / field names
3. Build tag-encode GUI + SBPL generator + USB send + encode-verify loop
