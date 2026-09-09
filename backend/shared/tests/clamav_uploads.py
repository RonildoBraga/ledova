import os
import socket

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError

from shared.tests.upload_fixtures import image_bytes, pdf_bytes
from shared.upload_errors import UploadRejected, UploadUnavailable
from shared.upload_scanner import scan_upload
from shared.uploads import validate_upload

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class RealClamAVUploadTest(SimpleTestCase):
    def setUp(self):
        scanner_settings = override_settings(
            UPLOAD_SCANNER_HOST=os.environ["UPLOAD_TEST_CLAMAV_HOST"],
            UPLOAD_SCANNER_PORT=int(os.environ.get("UPLOAD_TEST_CLAMAV_PORT", 3310)),
        )
        scanner_settings.enable()
        self.addCleanup(scanner_settings.disable)

    def test_real_clean_documents_scan_and_decode_without_changing_original_bytes(self):
        for name, mime, raw in (
            ("synthetic.pdf", "application/pdf", pdf_bytes()),
            ("synthetic.png", "image/png", image_bytes()),
            ("synthetic.jpg", "image/jpeg", image_bytes("JPEG")),
        ):
            with self.subTest(mime=mime):
                upload = SimpleUploadedFile(name, raw, content_type=mime)
                self.assertEqual(validate_upload(upload), (len(raw), mime))
                self.assertEqual(upload.read(), raw)

    def test_the_real_signature_engine_rejects_eicar(self):
        with self.assertRaises(UploadRejected):
            scan_upload(EICAR)

    def test_eicar_labeled_as_a_pdf_is_refused_by_the_upload_validator(self):
        upload = SimpleUploadedFile("synthetic.pdf", EICAR, content_type="application/pdf")

        with self.assertRaises(ValidationError) as refused:
            validate_upload(upload)

        self.assertIn("malware safety check", str(refused.exception))
        self.assertNotIn("Eicar", str(refused.exception))

    def test_an_unreachable_scanner_still_fails_closed_after_a_successful_scan(self):
        scan_upload(pdf_bytes())
        with socket.socket() as unavailable:
            unavailable.bind(("127.0.0.1", 0))
            with override_settings(UPLOAD_SCANNER_HOST="127.0.0.1", UPLOAD_SCANNER_PORT=unavailable.getsockname()[1]):
                with self.assertRaises(UploadUnavailable):
                    scan_upload(pdf_bytes())
