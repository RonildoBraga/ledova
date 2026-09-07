import os

from django.http import FileResponse, Http404

from shared.uploads import ALLOWED_UPLOAD_MIME_TYPES


def stream_stored_file(field, mime_type="", filename="", as_attachment=False):
    if not field:
        raise Http404("No file")
    try:
        handle = field.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("No file")
    content_type = mime_type or "application/octet-stream"
    return FileResponse(
        handle,
        as_attachment=as_attachment or content_type not in ALLOWED_UPLOAD_MIME_TYPES,
        content_type=content_type,
        filename=filename or os.path.basename(field.name),
    )
