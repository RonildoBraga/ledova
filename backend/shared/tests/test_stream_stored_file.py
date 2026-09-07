import io

from django.http import Http404
from django.test import SimpleTestCase

from shared.views import stream_stored_file


class StoredField:
    def __init__(self, name="evidence.pdf", payload=b"bytes"):
        self.name = name
        self._payload = payload

    def __bool__(self):
        return True

    def open(self, mode="rb"):
        return io.BytesIO(self._payload)


class StreamStoredFileDispositionTest(SimpleTestCase):

    @staticmethod
    def disposition(mime_type="", as_attachment=False):
        response = stream_stored_file(StoredField(), mime_type, as_attachment=as_attachment)
        return response.headers["Content-Disposition"]

    def test_a_pdf_is_rendered_in_the_browser(self):
        self.assertTrue(self.disposition("application/pdf").startswith("inline"))

    def test_a_png_is_rendered_in_the_browser(self):
        self.assertTrue(self.disposition("image/png").startswith("inline"))

    def test_a_jpeg_is_rendered_in_the_browser(self):
        self.assertTrue(self.disposition("image/jpeg").startswith("inline"))

    def test_html_is_downloaded_rather_than_rendered(self):
        self.assertTrue(self.disposition("text/html").startswith("attachment"))

    def test_svg_is_downloaded_rather_than_rendered(self):
        self.assertTrue(self.disposition("image/svg+xml").startswith("attachment"))

    def test_a_row_with_no_stored_type_is_downloaded(self):
        response = stream_stored_file(StoredField(), "")

        self.assertTrue(response.headers["Content-Disposition"].startswith("attachment"))
        self.assertEqual(response.headers["Content-Type"], "application/octet-stream")

    def test_a_caller_asking_for_an_attachment_still_gets_one(self):
        self.assertTrue(self.disposition("application/pdf", as_attachment=True).startswith("attachment"))

    def test_the_stored_type_is_served_unchanged_whichever_way_it_goes(self):
        rendered = stream_stored_file(StoredField(), "image/png")
        downloaded = stream_stored_file(StoredField(), "text/html")

        self.assertEqual(rendered.headers["Content-Type"], "image/png")
        self.assertEqual(downloaded.headers["Content-Type"], "text/html")

    def test_a_missing_field_is_still_404(self):
        with self.assertRaises(Http404):
            stream_stored_file(None, "application/pdf")
