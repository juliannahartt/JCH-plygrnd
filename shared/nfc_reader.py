"""
NFC reader interface for ACR122U via PC/SC (Windows).
Supports NTAG213 / NTAG215 / NTAG216.
"""

import time
import threading

try:
    from smartcard.System import readers as get_readers
    from smartcard.Exceptions import (
        CardConnectionException,
        NoReadersException,
        CardNotPresentException,
    )
    PYSCARD_AVAILABLE = True
except ImportError:
    PYSCARD_AVAILABLE = False


class NFCReaderError(Exception):
    pass


# ACR122U PN532 InDataExchange: read 16 bytes (4 pages) from NTAG21x
def _read_pages_cmd(start_page):
    return [0xFF, 0x00, 0x00, 0x00, 0x05, 0xD4, 0x40, 0x01, 0x30, start_page]


GET_UID_CMD = [0xFF, 0xCA, 0x00, 0x00, 0x00]


def list_readers():
    if not PYSCARD_AVAILABLE:
        return []
    try:
        return [str(r) for r in get_readers()]
    except NoReadersException:
        return []


def _transmit(connection, cmd):
    data, sw1, sw2 = connection.transmit(cmd)
    return bytes(data), sw1, sw2


def read_uid(connection):
    data, sw1, sw2 = _transmit(connection, GET_UID_CMD)
    if sw1 == 0x90:
        return data
    raise NFCReaderError(f"GET UID failed: SW={sw1:02X}{sw2:02X}")


def read_ntag_pages(connection, start_page):
    """
    Read 16 bytes (4 pages) from NTAG21x starting at start_page.
    Returns bytes or None on failure.
    """
    data, sw1, sw2 = _transmit(connection, _read_pages_cmd(start_page))
    # PN532 InDataExchange response: D5 41 <err> <data>
    if sw1 == 0x90 and len(data) >= 3 and data[0] == 0xD5 and data[1] == 0x41 and data[2] == 0x00:
        return data[3:]  # 16 bytes
    return None


def read_full_tag(connection):
    """
    Read UID, Capability Container (page 3), and all user memory pages.
    Returns a dict: {uid, uid_hex, cc, user_memory, tag_type}.
    """
    uid = read_uid(connection)
    uid_hex = uid.hex().upper()
    uid_fmt = ":".join(uid_hex[i:i+2] for i in range(0, len(uid_hex), 2))

    # Read page 3 (CC) + pages 4+ (user memory) in 4-page chunks
    pages = {}
    fail_streak = 0
    for start in range(3, 235, 4):
        chunk = read_ntag_pages(connection, start)
        if chunk is None:
            fail_streak += 1
            if fail_streak >= 2:
                break
            continue
        fail_streak = 0
        for i in range(4):
            pages[start + i] = chunk[i * 4: i * 4 + 4]

    cc = pages.get(3)
    tag_type = _identify_tag(cc)

    user_pages = {p: v for p, v in pages.items() if p >= 4}
    if user_pages:
        max_p = max(user_pages)
        user_memory = b"".join(user_pages.get(p, b"\x00" * 4) for p in range(4, max_p + 1))
    else:
        user_memory = b""

    return {
        "uid": uid,
        "uid_hex": uid_hex,
        "uid_fmt": uid_fmt,
        "cc": cc,
        "tag_type": tag_type,
        "user_memory": user_memory,
        "pages": pages,
    }


def _identify_tag(cc):
    if cc is None or len(cc) < 2:
        return "Unknown"
    if cc[0] != 0xE1:
        return "Non-NDEF / Unknown"
    size_byte = cc[2] if len(cc) > 2 else 0
    mapping = {0x12: "NTAG213", 0x3E: "NTAG215", 0x6D: "NTAG216"}
    return mapping.get(size_byte, f"NTAG (CC size=0x{size_byte:02X})")


class ContinuousScanner:
    """
    Runs a background thread that polls for NFC tags and fires callbacks.
    """

    def __init__(self, on_tag=None, on_status=None, reader_index=0):
        self.on_tag = on_tag          # callback(tag_dict)
        self.on_status = on_status    # callback(status_str)
        self.reader_index = reader_index
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _emit_status(self, msg):
        if self.on_status:
            self.on_status(msg)

    def _loop(self):
        if not PYSCARD_AVAILABLE:
            self._emit_status("ERROR: pyscard not installed — run: pip install pyscard")
            return

        while not self._stop.is_set():
            reader_list = []
            try:
                reader_list = get_readers()
            except NoReadersException:
                pass

            if not reader_list:
                self._emit_status("No reader found — check USB connection")
                time.sleep(2)
                continue

            reader = reader_list[min(self.reader_index, len(reader_list) - 1)]
            self._emit_status(f"Reader: {reader}  |  Waiting for tag...")

            conn = reader.createConnection()
            try:
                conn.connect()
            except CardNotPresentException:
                time.sleep(0.25)
                continue
            except Exception as e:
                self._emit_status(f"Reader error: {e}")
                time.sleep(1)
                continue

            # Tag present
            self._emit_status("Tag detected — reading...")
            try:
                tag = read_full_tag(conn)
                if self.on_tag:
                    self.on_tag(tag)
                self._emit_status(f"Tag read OK — UID: {tag['uid_fmt']}  |  Remove tag to scan next")
            except Exception as e:
                self._emit_status(f"Read error: {e}")

            # Wait for tag removal
            while not self._stop.is_set():
                try:
                    _transmit(conn, GET_UID_CMD)
                    time.sleep(0.4)
                except Exception:
                    break

            try:
                conn.disconnect()
            except Exception:
                pass

            time.sleep(0.1)
