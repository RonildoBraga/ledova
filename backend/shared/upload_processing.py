import json
from pathlib import Path

from django.conf import settings

from shared.upload_errors import UploadRejected, UploadUnavailable
from shared.upload_process import UploadProcessTimeout, run_upload_worker

WORKER = Path(__file__).with_name("upload_worker.py")
INVALID_CONTENT = "The file is not a valid, supported PDF, PNG or JPEG document."
PROCESSING_LIMIT = "The file exceeds the document processing limits."


def processing_limits():
    limits = {
        "input_bytes": settings.UPLOAD_MAX_BYTES,
        "pages": settings.UPLOAD_MAX_PDF_PAGES,
        "pixels": settings.UPLOAD_MAX_SOURCE_PIXELS,
        "decoded_bytes": settings.UPLOAD_MAX_DECODED_BYTES,
        "side": settings.UPLOAD_RENDER_MAX_SIDE,
        "output_bytes": settings.UPLOAD_RENDER_MAX_BYTES,
        "memory_bytes": settings.UPLOAD_PROCESS_MEMORY_BYTES,
        "cpu_seconds": settings.UPLOAD_PROCESS_CPU_SECONDS,
    }
    if any(value < 1 for value in limits.values()) or settings.UPLOAD_PROCESS_WALL_SECONDS < 1:
        raise UploadUnavailable()
    return limits


def process_upload(raw, mode="inspect"):
    limits = processing_limits()
    if not raw or len(raw) > limits["input_bytes"]:
        raise UploadRejected(PROCESSING_LIMIT)
    limit = limits["output_bytes"] if mode == "render" else 1024
    try:
        returncode, value = run_upload_worker(
            WORKER, [mode, json.dumps(limits)], raw, settings.UPLOAD_PROCESS_WALL_SECONDS, limit
        )
    except UploadProcessTimeout:
        raise UploadRejected(PROCESSING_LIMIT) from None
    if returncode:
        raise UploadRejected(INVALID_CONTENT if returncode == 2 else PROCESSING_LIMIT)
    if not value or len(value) > limit:
        raise UploadRejected(PROCESSING_LIMIT)
    if mode == "render":
        if not value.startswith(b"\x89PNG\r\n\x1a\n"):
            raise UploadRejected(INVALID_CONTENT)
        return value
    try:
        return json.loads(value)["mime_type"]
    except (ValueError, KeyError, TypeError):
        raise UploadRejected(INVALID_CONTENT) from None
