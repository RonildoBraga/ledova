import io
from unittest.mock import patch

import pymupdf
from PIL import Image


class StubUploadDependencies:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for target in (
            "shared.uploads.scan_upload",
            "documents.services.extraction.scan_upload",
            "shared.upload_limits.reserve_request",
            "shared.upload_limits.reserve_bytes",
        ):
            stub = patch(target)
            stub.start()
            cls.addClassCleanup(stub.stop)


def pdf_bytes(pages=1, width=595, height=842):
    with pymupdf.open() as document:
        for _ in range(pages):
            document.new_page(width=width, height=height)
        return document.tobytes()


def image_bytes(format="PNG", size=(32, 24)):
    output = io.BytesIO()
    with Image.new("RGB", size, "white") as image:
        image.save(output, format=format)
    return output.getvalue()


def pdf_with_images(sizes):
    with pymupdf.open() as document:
        page = document.new_page(width=5, height=5)
        for size in sizes:
            page.insert_image(pymupdf.Rect(0, 0, 5, 5), stream=image_bytes(size=size))
        return document.tobytes()
