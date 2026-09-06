import os

from django.http import FileResponse, Http404


def stream_stored_file(field, mime_type="", filename=""):
    if not field:
        raise Http404("No file")
    try:
        handle = field.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("No file")
    return FileResponse(
        handle,
        content_type=mime_type or "application/octet-stream",
        filename=filename or os.path.basename(field.name),
    )
