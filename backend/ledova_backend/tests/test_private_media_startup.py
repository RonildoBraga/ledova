import asyncio
import runpy
from pathlib import Path

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, TransactionTestCase, override_settings

from authentication.services import TokenService
from documents.tests.test_document_file_access import (
    DOCUMENT_BYTES,
    make_document,
    make_user,
)
from shared.upload_gateway import BoundedUploadASGI, BoundedUploadWSGI


@override_settings(DEBUG=False, STORAGE_BACKEND="local")
class LocalPrivateMediaStartupTest(TransactionTestCase):
    def setUp(self):
        owner = make_user("startup-owner")
        stranger = make_user("startup-stranger")
        self.owner_token = TokenService.issue(owner)[0]
        self.stranger_token = TokenService.issue(stranger)[0]
        self.document = make_document(owner)
        self.url = f"/api/v1/documents/{self.document.uuid}/file/"

    def application(self, entrypoint):
        with override_settings(RLS_AMBIENT_ALIAS="app"):
            return runpy.run_path(str(Path(settings.BASE_DIR) / "ledova_backend" / entrypoint))["application"]

    def wsgi_response(self, application, path, token):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        request = RequestFactory().get(path, **headers)
        status = []

        def start_response(value, response_headers, exc_info=None):
            status.append(int(value.split()[0]))

        response = application(request.environ, start_response)
        try:
            return status[0], b"".join(response)
        finally:
            response.close()

    async def asgi_response(self, application, path, token):
        headers = [(b"host", b"testserver")]
        if token:
            headers.append((b"authorization", f"Bearer {token}".encode()))
        scope = {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": headers,
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
        }
        received = False
        responses = []

        async def receive():
            nonlocal received
            if received:
                await asyncio.Event().wait()
            received = True
            return {"type": "http.request", "body": b""}

        async def send(message):
            responses.append(message)

        await asyncio.wait_for(application(scope, receive, send), timeout=5)
        return responses[0]["status"], b"".join(message.get("body", b"") for message in responses)

    def assert_private_access(self, application, request):
        status, body = request(application, self.url, self.owner_token)
        self.assertEqual((status, body), (200, DOCUMENT_BYTES))
        self.assertEqual(request(application, self.url, self.stranger_token)[0], 404)
        self.assertEqual(request(application, self.url, None)[0], 401)
        self.assertEqual(request(application, f"/media/{self.document.file.name}", None)[0], 404)

    def test_wsgi_starts_without_debug_and_streams_local_evidence_only_to_its_owner(self):
        application = self.application("wsgi.py")
        self.assertIsInstance(application, BoundedUploadWSGI)
        self.assert_private_access(application, self.wsgi_response)

    def test_asgi_starts_without_debug_and_streams_local_evidence_only_to_its_owner(self):
        application = self.application("asgi.py")
        self.assertIsInstance(application, BoundedUploadASGI)
        self.assert_private_access(application, async_to_sync(self.asgi_response))

    def test_both_entrypoints_still_refuse_an_operator_request_connection(self):
        for entrypoint in ("wsgi.py", "asgi.py"):
            with self.subTest(entrypoint=entrypoint), override_settings(RLS_AMBIENT_ALIAS="operator"):
                with self.assertRaisesMessage(ImproperlyConfigured, "row-level security bypassed"):
                    runpy.run_path(str(Path(settings.BASE_DIR) / "ledova_backend" / entrypoint))
