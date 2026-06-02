tag-encode
==========
Printing and NFC encoding app for BIB labels.
Hardware target: SATO CL4NX Plus 203dpi + ACR122U (or ACR1252U) for encode-verify.

Fields to encode per tag:
  - UUID         : tag UID (read-back from chip after print, not pre-written)
  - mfg_date     : today's date (MMDDYYYY or ISO 8601)
  - exp_date     : mfg_date + 1 year
  - flavor_number: entered by operator / pulled from job
  - copacker_id  : entered by operator / pulled from job
  - validity     : "valid" (set at encode time; invalidated if tag later fails verify)

To be developed in the next session.
Dependencies will include: pyscard, ZPL generation for SATO CL4NX.
