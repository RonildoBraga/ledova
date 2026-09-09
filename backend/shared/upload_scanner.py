import json
from pathlib import Path

from django.conf import settings

from shared.upload_errors import UploadRejected, UploadUnavailable
from shared.upload_process import UploadProcessTimeout, run_upload_worker

WORKER = Path(__file__).with_name("upload_scanner_worker.py")
SCANNER_REPLY_BYTES = 4096


def scan_upload(raw):
    if (
        not settings.UPLOAD_SCANNER_HOST
        or settings.UPLOAD_SCANNER_SECONDS < 1
        or not raw
        or len(raw) > settings.UPLOAD_MAX_BYTES
    ):
        raise UploadUnavailable()
    parameters = {
        "host": settings.UPLOAD_SCANNER_HOST,
        "port": settings.UPLOAD_SCANNER_PORT,
        "seconds": settings.UPLOAD_SCANNER_SECONDS,
        "input_bytes": settings.UPLOAD_MAX_BYTES,
        "memory_bytes": settings.UPLOAD_PROCESS_MEMORY_BYTES,
        "cpu_seconds": settings.UPLOAD_PROCESS_CPU_SECONDS,
        "reply_bytes": SCANNER_REPLY_BYTES,
    }
    try:
        returncode, reply = run_upload_worker(
            WORKER, [json.dumps(parameters)], raw, settings.UPLOAD_SCANNER_SECONDS, SCANNER_REPLY_BYTES
        )
    except UploadProcessTimeout:
        raise UploadUnavailable() from None
    if returncode or len(reply) > SCANNER_REPLY_BYTES:
        raise UploadUnavailable()
    if reply == b"stream: OK\0":
        return
    if reply.startswith(b"stream: ") and reply.endswith(b" FOUND\0") and reply.count(b"\0") == 1:
        raise UploadRejected("The file failed the malware safety check.")
    raise UploadUnavailable()
