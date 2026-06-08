"""
SATO CL4NX Plus USB interface using pyusb (libusb).

Matches the claim/release pattern used by TagPrinter 2.3:
  Claiming the USB interface → send SBPL → Releasing printer

Requires libusb-1.0 on Windows. If the existing TagPrinter 2.3 app works
via direct USB, libusb is already installed — pyusb will use the same backend.

If you see a USBError about no backend: install libusb via Zadig (zadig.akeo.ie)
and select the SATO printer, backend = libusb-win32 or WinUSB.
"""

import time
from typing import Optional

try:
    import usb.core
    import usb.util
    import usb.backend.libusb1 as libusb1
    PYUSB_AVAILABLE = True
except ImportError:
    PYUSB_AVAILABLE = False


SATO_VENDOR_ID   = 0x0828
CL4NX_PRODUCT_ID = 0x0158
WRITE_TIMEOUT_MS = 30_000  # 30 s — NFC encode takes ~15 s


class PrinterNotFoundError(Exception):
    pass


class PrinterError(Exception):
    pass


class SatoPrinter:
    """Wraps a single SATO CL4NX Plus USB device."""

    def __init__(self):
        if not PYUSB_AVAILABLE:
            raise RuntimeError("pyusb not installed. Run: pip install pyusb")
        self._dev: Optional["usb.core.Device"] = None
        self._intf = None
        self._ep_out = None

    # ── Discovery ─────────────────────────────────────────────

    @staticmethod
    def find_all() -> list[dict]:
        """Return list of SATO CL4NX devices found on USB bus."""
        if not PYUSB_AVAILABLE:
            return []
        devices = usb.core.find(idVendor=SATO_VENDOR_ID, find_all=True)
        return [
            {"vendor_id": hex(d.idVendor), "product_id": hex(d.idProduct), "bus": d.bus, "address": d.address}
            for d in (devices or [])
        ]

    @staticmethod
    def is_available() -> bool:
        if not PYUSB_AVAILABLE:
            return False
        return usb.core.find(idVendor=SATO_VENDOR_ID, idProduct=CL4NX_PRODUCT_ID) is not None

    # ── Connect / disconnect ───────────────────────────────────

    def connect(self):
        dev = usb.core.find(idVendor=SATO_VENDOR_ID, idProduct=CL4NX_PRODUCT_ID)
        if dev is None:
            raise PrinterNotFoundError(
                f"SATO CL4NX Plus not found (VID={SATO_VENDOR_ID:#06x}, PID={CL4NX_PRODUCT_ID:#06x}). "
                "Check USB cable and ensure TagPrinter 2.3 is closed."
            )

        # On Windows the device may already have a kernel driver attached;
        # detach only needed on Linux/Mac but harmless to attempt.
        for cfg in dev:
            for intf in cfg:
                if dev.is_kernel_driver_active(intf.bInterfaceNumber):
                    try:
                        dev.detach_kernel_driver(intf.bInterfaceNumber)
                    except Exception:
                        pass

        dev.set_configuration()
        cfg  = dev.get_active_configuration()
        intf = cfg[(0, 0)]

        ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
            == usb.util.ENDPOINT_OUT,
        )
        if ep_out is None:
            raise PrinterError("Could not find USB OUT endpoint on SATO device.")

        usb.util.claim_interface(dev, intf)

        self._dev    = dev
        self._intf   = intf
        self._ep_out = ep_out

    def disconnect(self):
        if self._dev and self._intf is not None:
            try:
                usb.util.release_interface(self._dev, self._intf)
            except Exception:
                pass
            try:
                usb.util.dispose_resources(self._dev)
            except Exception:
                pass
        self._dev    = None
        self._intf   = None
        self._ep_out = None

    # ── Send ──────────────────────────────────────────────────

    def send_raw(self, data: bytes):
        if self._dev is None or self._ep_out is None:
            raise PrinterError("Not connected. Call connect() first.")
        self._dev.write(self._ep_out.bEndpointAddress, data, timeout=WRITE_TIMEOUT_MS)

    # ── High-level ────────────────────────────────────────────

    def print_sbpl(self, sbpl: str, on_status: callable | None = None):
        """
        Claim USB, send SBPL, release USB.
        on_status(msg: str) is called with progress messages if provided.
        """
        def status(msg):
            if on_status:
                on_status(msg)

        status("Connecting to printer...")
        self.connect()
        status("Printer claimed — sending job...")
        try:
            self.send_raw(sbpl.encode("ascii", errors="replace"))
            status("Job sent — encoding NFC tag...")
            # The CL4NX takes ~15 s to complete encode+print.
            # We wait here so the USB interface stays claimed until done.
            time.sleep(16)
            status("Print job complete.")
        finally:
            self.disconnect()
            status("Printer released.")
