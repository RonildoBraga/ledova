import os

from rest_framework import serializers

MAX_UPLOAD_SIZE = 10 * 1024 * 1024
ALLOWED_UPLOAD_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg"}
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def validate_upload(file, field="file"):
    if file.size > MAX_UPLOAD_SIZE:
        raise serializers.ValidationError({field: "File size must not exceed 10 MB."})

    mime = file.content_type or ""
    if mime not in ALLOWED_UPLOAD_MIME_TYPES:
        raise serializers.ValidationError({field: "Only PDF and image files (PNG, JPEG) are allowed."})

    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise serializers.ValidationError({field: "Only .pdf, .png, .jpg, .jpeg files are allowed."})

    return file.size, mime
