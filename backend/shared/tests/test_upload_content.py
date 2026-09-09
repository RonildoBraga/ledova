import io
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image
from rest_framework import serializers

from shared.tests.upload_fixtures import image_bytes, pdf_bytes, pdf_with_images
from shared.upload_errors import UploadRejected
from shared.upload_processing import WORKER, process_upload
from shared.uploads import read_bounded, validate_upload


class UploadContentTest(SimpleTestCase):
    def setUp(self):
        scanner = patch("shared.uploads.scan_upload")
        self.scanner = scanner.start()
        self.addCleanup(scanner.stop)

    def test_a_real_pdf_png_and_jpeg_are_accepted_without_changing_their_bytes(self):
        for name, mime, raw in (
            ("document.pdf", "application/pdf", pdf_bytes()),
            ("document.png", "image/png", image_bytes()),
            ("document.jpg", "image/jpeg", image_bytes("JPEG")),
        ):
            with self.subTest(name=name):
                upload = SimpleUploadedFile(name, raw, content_type=mime)

                self.assertEqual(validate_upload(upload), (len(raw), mime))
                self.assertEqual(upload.read(), raw)

    def test_a_pdf_label_does_not_admit_arbitrary_bytes(self):
        upload = SimpleUploadedFile("document.pdf", b"<html>synthetic payload</html>", content_type="application/pdf")

        with self.assertRaises(serializers.ValidationError):
            validate_upload(upload)

    def test_the_detected_format_must_match_both_the_declared_mime_and_extension(self):
        for name, mime in (("document.pdf", "application/pdf"), ("document.png", "application/pdf")):
            with self.subTest(name=name, mime=mime):
                upload = SimpleUploadedFile(name, image_bytes(), content_type=mime)

                with self.assertRaises(serializers.ValidationError):
                    validate_upload(upload)

    def test_a_truncated_pdf_is_not_a_valid_document(self):
        upload = SimpleUploadedFile("document.pdf", b"%PDF-1.4 body", content_type="application/pdf")

        with self.assertRaises(serializers.ValidationError):
            validate_upload(upload)

    @override_settings(UPLOAD_MAX_PDF_PAGES=1)
    def test_the_page_limit_refuses_a_real_two_page_pdf_and_accepts_one_page(self):
        for pages, accepted in ((1, True), (2, False)):
            with self.subTest(pages=pages):
                upload = SimpleUploadedFile("document.pdf", pdf_bytes(pages), content_type="application/pdf")
                if accepted:
                    self.assertEqual(validate_upload(upload)[1], "application/pdf")
                else:
                    with self.assertRaises(serializers.ValidationError):
                        validate_upload(upload)

    @override_settings(UPLOAD_MAX_SOURCE_PIXELS=768)
    def test_the_pixel_limit_is_checked_before_a_valid_image_is_decoded(self):
        upload = SimpleUploadedFile("document.png", image_bytes(size=(32, 24)), content_type="image/png")
        self.assertEqual(validate_upload(upload)[1], "image/png")
        upload = SimpleUploadedFile("document.png", image_bytes(size=(33, 24)), content_type="image/png")

        with self.assertRaises(serializers.ValidationError):
            validate_upload(upload)

    @override_settings(UPLOAD_MAX_DECODED_BYTES=1024)
    def test_the_decompressed_byte_limit_is_independent_of_the_compressed_file_size(self):
        self.assertEqual(process_upload(image_bytes(size=(16, 16))), "image/png")

        with self.assertRaises(UploadRejected):
            process_upload(image_bytes(size=(17, 16)))

    @override_settings(UPLOAD_MAX_SOURCE_PIXELS=40000)
    def test_pdf_page_dimensions_are_bounded_before_rendering(self):
        self.assertEqual(process_upload(pdf_bytes(width=100, height=100)), "application/pdf")

        with self.assertRaises(UploadRejected):
            process_upload(pdf_bytes(width=101, height=100))

    @override_settings(UPLOAD_MAX_SOURCE_PIXELS=120)
    def test_a_small_pdf_page_cannot_hide_an_oversized_embedded_image(self):
        self.assertEqual(process_upload(pdf_with_images([(10, 10)])), "application/pdf")
        with self.assertRaises(UploadRejected):
            process_upload(pdf_with_images([(13, 10)]))

    @override_settings(UPLOAD_MAX_DECODED_BYTES=600)
    def test_a_pdf_page_cannot_accumulate_unbounded_decoded_images(self):
        self.assertEqual(process_upload(pdf_with_images([(10, 10)])), "application/pdf")
        with self.assertRaises(UploadRejected):
            process_upload(pdf_with_images([(10, 10), (11, 10)]))

    def test_an_encrypted_pdf_is_refused(self):
        import pymupdf

        with pymupdf.open(stream=pdf_bytes(), filetype="pdf") as document:
            encrypted = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="synthetic-password")

        with self.assertRaises(UploadRejected):
            process_upload(encrypted)

    def test_truncated_image_data_does_not_pass_a_magic_byte_check(self):
        for format in ("PNG", "JPEG"):
            with self.subTest(format=format):
                with self.assertRaises(UploadRejected):
                    process_upload(image_bytes(format)[:40])

    def test_a_false_size_cannot_hide_bytes_over_the_file_limit(self):
        raw = image_bytes()
        upload = SimpleUploadedFile("document.png", raw, content_type="image/png")
        upload.size = 1

        with override_settings(UPLOAD_MAX_BYTES=len(raw) - 1), self.assertRaises(serializers.ValidationError):
            validate_upload(upload)
        self.scanner.assert_not_called()

    def test_the_reader_never_consumes_more_than_the_limit_and_one_control_byte(self):
        stream = io.BytesIO(b"abcdefghij")

        with override_settings(UPLOAD_MAX_BYTES=4), self.assertRaises(UploadRejected):
            read_bounded(stream)

        self.assertEqual(stream.tell(), 5)
        with override_settings(UPLOAD_MAX_BYTES=4):
            self.assertEqual(read_bounded(io.BytesIO(b"abcd")), b"abcd")


class UploadRendererTest(SimpleTestCase):
    def test_clean_pdf_and_image_render_with_the_default_process_limits(self):
        for raw in (pdf_bytes(), image_bytes(), image_bytes("JPEG")):
            with self.subTest(signature=raw[:8]):
                rendered = process_upload(raw, mode="render")
                with Image.open(io.BytesIO(rendered)) as image:
                    self.assertEqual(image.format, "PNG")
                    self.assertLessEqual(max(image.size), 1600)
                    self.assertGreater(min(image.size), 0)

    def test_stored_mime_and_filename_cannot_select_the_wrong_decoder(self):
        from documents.services.extraction import ExtractionService

        document = SimpleNamespace(mime_type="application/pdf", original_filename="document.pdf")
        with patch("documents.services.extraction.scan_upload"):
            rendered = ExtractionService.render_first_page(document, image_bytes())

        with Image.open(io.BytesIO(rendered)) as image:
            self.assertEqual(image.size, (32, 24))

    @override_settings(UPLOAD_RENDER_MAX_SIDE=16)
    def test_pdf_and_image_outputs_obey_the_configured_render_size(self):
        for raw in (pdf_bytes(), image_bytes()):
            with self.subTest(signature=raw[:8]):
                with Image.open(io.BytesIO(process_upload(raw, mode="render"))) as image:
                    self.assertLessEqual(max(image.size), 16)

    def test_a_real_decoder_cannot_run_with_an_insufficient_address_space_budget(self):
        raw = pdf_bytes()
        self.assertEqual(process_upload(raw), "application/pdf")

        with override_settings(UPLOAD_PROCESS_MEMORY_BYTES=32 * 1024 * 1024), self.assertRaises(UploadRejected):
            process_upload(raw)

    def test_rendered_output_bytes_have_a_separate_limit(self):
        raw = image_bytes()
        self.assertGreater(len(process_upload(raw, mode="render")), 16)
        with override_settings(UPLOAD_RENDER_MAX_BYTES=16), self.assertRaises(UploadRejected):
            process_upload(raw, mode="render")

    @override_settings(UPLOAD_PROCESS_WALL_SECONDS=5)
    def test_the_workers_cpu_limit_interrupts_work_before_the_wall_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = Path(directory) / "cpu_probe.py"
            worker.write_text(
                "import runpy\nimport sys\nimport time\n"
                f"worker = runpy.run_path({str(WORKER)!r})\n"
                "def burn(*args):\n"
                "    started = time.process_time()\n"
                "    while time.process_time() - started < 2:\n"
                "        pass\n"
                "    return 'image/png'\n"
                "worker['main'].__globals__['process_image'] = burn\n"
                "sys.exit(worker['main']())\n"
            )
            with patch("shared.upload_processing.WORKER", worker):
                with override_settings(UPLOAD_PROCESS_CPU_SECONDS=3):
                    self.assertEqual(process_upload(image_bytes()), "image/png")
                with override_settings(UPLOAD_PROCESS_CPU_SECONDS=1), self.assertRaises(UploadRejected):
                    process_upload(image_bytes())

    @override_settings(UPLOAD_PROCESS_WALL_SECONDS=1)
    def test_the_parent_terminates_a_decoder_that_does_not_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = Path(directory) / "slow.py"
            worker.write_text('import time\ntime.sleep(2)\nprint(\'{"mime_type": "image/png"}\')\n')
            with patch("shared.upload_processing.WORKER", worker), self.assertRaises(UploadRejected):
                process_upload(image_bytes())
