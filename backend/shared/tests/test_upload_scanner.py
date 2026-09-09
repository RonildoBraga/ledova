import socket
import struct
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from shared.upload_errors import UploadRejected, UploadUnavailable
from shared.upload_scanner import scan_upload


class ScannerProtocolTest(SimpleTestCase):
    def scanner_reply(self, raw, reply):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(3)
        received = []

        def serve():
            server, _ = listener.accept()
            with server, server.makefile("rb") as source:
                command = source.read(10)
                data = bytearray()
                while True:
                    length = struct.unpack("!I", source.read(4))[0]
                    if length == 0:
                        break
                    data.extend(source.read(length))
                received.append((command, bytes(data)))
                server.sendall(reply)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            with override_settings(UPLOAD_SCANNER_HOST="127.0.0.1", UPLOAD_SCANNER_PORT=listener.getsockname()[1]):
                scan_upload(raw)
        finally:
            listener.close()
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        return received

    def test_the_client_streams_all_bytes_and_accepts_one_complete_clean_verdict(self):
        raw = b"synthetic bytes" * 10000

        received = self.scanner_reply(raw, b"stream: OK\0")

        self.assertEqual(received, [(b"zINSTREAM\0", raw)])

    def test_a_detection_verdict_refuses_the_file_without_exposing_the_signature(self):
        with self.assertRaises(UploadRejected) as refused:
            self.scanner_reply(b"synthetic", b"stream: synthetic-sensitive-signature FOUND\0")

        self.assertNotIn("synthetic-sensitive-signature", str(refused.exception))

    def test_truncated_error_extra_and_oversized_replies_fail_closed(self):
        for reply in (
            b"stream: OK",
            b"stream: ERROR\0",
            b"stream: OK\0stream: a detection FOUND\0",
            b"stream: OK\0" + b"x" * 4096,
            b"",
        ):
            with self.subTest(reply=reply[:20]), self.assertRaises(UploadUnavailable):
                self.scanner_reply(b"synthetic", reply)

    def test_an_unavailable_daemon_fails_closed(self):
        with socket.socket() as unavailable:
            unavailable.bind(("127.0.0.1", 0))
            with override_settings(UPLOAD_SCANNER_HOST="127.0.0.1", UPLOAD_SCANNER_PORT=unavailable.getsockname()[1]):
                with self.assertRaises(UploadUnavailable) as refused:
                    scan_upload(b"synthetic")

        self.assertNotIn("127.0.0.1", str(refused.exception))

    @override_settings(UPLOAD_SCANNER_SECONDS=1)
    def test_a_daemon_that_never_replies_has_a_real_deadline(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            with override_settings(UPLOAD_SCANNER_HOST="127.0.0.1", UPLOAD_SCANNER_PORT=listener.getsockname()[1]):
                with self.assertRaises(UploadUnavailable):
                    scan_upload(b"synthetic")

    @override_settings(UPLOAD_SCANNER_SECONDS=1)
    def test_the_parent_deadline_also_terminates_a_blocked_resolver_process(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = Path(directory) / "blocked_resolver.py"
            worker.write_text("import time\ntime.sleep(3)\nprint('stream: OK\\0', end='')\n")
            started = time.monotonic()
            with patch("shared.upload_scanner.WORKER", worker), self.assertRaises(UploadUnavailable):
                scan_upload(b"synthetic")
            self.assertLess(time.monotonic() - started, 2.5)
