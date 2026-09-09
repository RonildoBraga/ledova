import os

from django.conf import settings
from rest_framework import serializers

from shared.upload_errors import UploadRejected
from shared.upload_processing import process_upload
from shared.upload_scanner import scan_upload

MAX_UPLOAD_SIZE = settings.UPLOAD_MAX_BYTES
ALLOWED_UPLOAD_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg"}
UPLOAD_MIME_BY_EXTENSION = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
ALLOWED_UPLOAD_EXTENSIONS = set(UPLOAD_MIME_BY_EXTENSION)


def upload_size_error():
    return f"File size must not exceed {settings.UPLOAD_MAX_BYTES / (1024 * 1024):g} MB."


def read_bounded(stream):
    limit = settings.UPLOAD_MAX_BYTES
    raw = bytearray()
    while len(raw) <= limit:
        chunk = stream.read(min(65536, limit + 1 - len(raw)))
        if not chunk:
            return bytes(raw)
        raw.extend(chunk)
    raise UploadRejected(upload_size_error())


def validate_upload(file, field="file"):
    if file.size > settings.UPLOAD_MAX_BYTES:
        raise serializers.ValidationError({field: upload_size_error()})

    mime = file.content_type or ""
    if mime not in ALLOWED_UPLOAD_MIME_TYPES:
        raise serializers.ValidationError({field: "Only PDF and image files (PNG, JPEG) are allowed."})

    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise serializers.ValidationError({field: "Only .pdf, .png, .jpg, .jpeg files are allowed."})

    try:
        file.seek(0)
        raw = read_bounded(file)
        scan_upload(raw)
        detected = process_upload(raw)
        if detected != mime or UPLOAD_MIME_BY_EXTENSION[ext] != detected:
            raise UploadRejected("The file content must match its PDF, PNG or JPEG type and extension.")
        return len(raw), detected
    except UploadRejected as error:
        raise serializers.ValidationError({field: str(error)}) from None
    finally:
        file.seek(0)
