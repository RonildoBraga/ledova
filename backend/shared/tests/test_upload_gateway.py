import asyncio
import io
from unittest.mock import Mock, patch

from django.core.exceptions import RequestDataTooBig
from django.core.handlers.asgi import ASGIHandler
from django.http import HttpResponse
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import get_resolver
from rest_framework.generics import GenericAPIView
from rest_framework.serializers import FileField

from shared.tests.test_route_coverage import _walk
from shared.upload_gateway import (
    BoundedUploadASGI,
    BoundedUploadInput,
    BoundedUploadWSGI,
    asgi_path_info,
    is_upload_request,
)
from shared.views.uploads import UploadProtectedView


class UploadRouteCoverageTest(TestCase):
    def test_every_writable_file_serializer_is_protected_before_multipart_parsing(self):
        found = set()
        for _, callback in _walk(get_resolver().url_patterns):
            view = getattr(callback, "cls", None)
            actions = getattr(callback, "actions", {})
            if view is None or not hasattr(view, "get_serializer_class"):
                continue
            for method, action in actions.items():
                if method not in ("post", "put", "patch") or method not in view.http_method_names:
                    continue
                instance = view(**getattr(callback, "initkwargs", {}))
                instance.action = action
                instance.request = None
                if (
                    instance.serializer_class is None
                    and view.get_serializer_class is GenericAPIView.get_serializer_class
                ):
                    continue
                serializer = instance.get_serializer_class()()
                fields = {
                    name
                    for name, field in serializer.fields.items()
                    if isinstance(field, FileField) and not field.read_only
                }
                if fields:
                    with self.subTest(view=view, action=action):
                        self.assertTrue(issubclass(view, UploadProtectedView))
                        self.assertEqual((method, action), ("post", "create"))
                        self.assertEqual(fields, {view.upload_field})
                    found.add(view)
        self.assertEqual(len(found), 3)

    def test_the_gateway_resolves_all_three_upload_routes_and_leaves_reads_alone(self):
        for path in (
            "/api/v1/documents/",
            "/api/v1/companies/00000000-0000-0000-0000-000000000001/documents/",
            "/api/investor-classifications/",
        ):
            self.assertTrue(is_upload_request(path, "POST"))
            self.assertFalse(is_upload_request(path, "GET"))
        self.assertFalse(is_upload_request("/api/v1/documents/00000000-0000-0000-0000-000000000001/attach/", "POST"))

    def test_script_prefix_stripping_uses_a_complete_path_segment(self):
        self.assertEqual(asgi_path_info({"path": "/ledova", "root_path": "/ledova/"}), "")
        self.assertEqual(asgi_path_info({"path": "/ledova-other/api/", "root_path": "/ledova"}), "/ledova-other/api/")


@override_settings(UPLOAD_MAX_REQUEST_BYTES=16, UPLOAD_BODY_SECONDS=0.1)
class UploadASGIIngressTest(SimpleTestCase):
    async def request(self, chunks, declared=None, prefix=""):
        scope = {
            "type": "http",
            "method": "POST",
            "path": prefix + "/api/v1/documents/",
            "root_path": prefix,
            "headers": [] if declared is None else [(b"content-length", declared)],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
        }
        messages = iter(chunks)
        responses = []
        received_by_view = []

        async def receive():
            message = next(messages, None)
            if message is None:
                await asyncio.Event().wait()
            return message

        async def send(message):
            responses.append(message)

        async def respond(request):
            received_by_view.append(request.body)
            return HttpResponse("synthetic accepted")

        application = ASGIHandler()
        with patch.object(application, "run_get_response", side_effect=respond):
            await asyncio.wait_for(BoundedUploadASGI(application)(scope, receive, send), timeout=2)
        return responses, received_by_view

    async def test_an_exact_limit_body_reaches_the_real_django_handler(self):
        responses, body = await self.request([{"type": "http.request", "body": b"x" * 16}])

        self.assertEqual(responses[0]["status"], 200)
        self.assertEqual(body, [b"x" * 16])

    async def test_chunked_and_false_declared_sizes_stop_before_django_dispatch(self):
        for declared in (None, b"1"):
            with self.subTest(declared=declared):
                responses, body = await self.request(
                    [
                        {"type": "http.request", "body": b"x" * 16, "more_body": True},
                        {"type": "http.request", "body": b"x", "more_body": False},
                    ],
                    declared,
                )
                self.assertEqual(responses[0]["status"], 413)
                self.assertEqual(body, [])

    async def test_a_large_or_invalid_declared_size_is_refused_without_receiving(self):
        for declared in (b"17", b"-1", b"invalid"):
            responses, body = await self.request([], declared)
            self.assertEqual(responses[0]["status"], 413)
            self.assertEqual(body, [])

    async def test_a_stalled_body_has_a_real_deadline_before_dispatch(self):
        responses, body = await self.request([{"type": "http.request", "body": b"x", "more_body": True}])

        self.assertEqual(responses[0]["status"], 408)
        self.assertEqual(body, [])

    async def test_a_mounted_application_has_the_same_pre_spooling_limit(self):
        allowed, body = await self.request([{"type": "http.request", "body": b"x" * 16}], prefix="/ledova")
        self.assertEqual(allowed[0]["status"], 200)
        self.assertEqual(body, [b"x" * 16])

        refused, body = await self.request([{"type": "http.request", "body": b"x" * 17}], prefix="/ledova")
        self.assertEqual(refused[0]["status"], 413)
        self.assertEqual(body, [])

    @override_settings(FORCE_SCRIPT_NAME="/ledova")
    async def test_the_configured_script_name_has_the_same_pre_spooling_limit(self):
        refused, body = await self.request([{"type": "http.request", "body": b"x" * 17}], prefix="/ledova")
        self.assertEqual(refused[0]["status"], 413)
        self.assertEqual(body, [])


@override_settings(UPLOAD_MAX_REQUEST_BYTES=16)
class UploadWSGIIngressTest(SimpleTestCase):
    def test_an_unbounded_read_consumes_only_the_limit_and_one_control_byte(self):
        raw = io.BytesIO(b"x" * 1000)
        stream = BoundedUploadInput(raw)

        with self.assertRaises(RequestDataTooBig):
            stream.read()

        self.assertEqual(raw.tell(), 17)
        self.assertEqual(BoundedUploadInput(io.BytesIO(b"x" * 16)).read(), b"x" * 16)

    def test_cumulative_line_reads_are_also_bounded(self):
        stream = BoundedUploadInput(io.BytesIO(b"1234567\n" * 3))
        self.assertEqual(stream.readline(), b"1234567\n")
        self.assertEqual(stream.readline(), b"1234567\n")
        with self.assertRaises(RequestDataTooBig):
            stream.readline()

    def test_the_wrapper_refuses_a_large_header_before_calling_django(self):
        application = Mock()
        start = Mock()
        BoundedUploadWSGI(application)(
            {"REQUEST_METHOD": "POST", "PATH_INFO": "/api/v1/documents/", "CONTENT_LENGTH": "17"}, start
        )
        application.assert_not_called()
        self.assertEqual(start.call_args.args[0], "413 Content Too Large")

    def test_an_allowed_header_installs_the_counting_stream(self):
        application = Mock()
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/api/v1/documents/",
            "CONTENT_LENGTH": "1",
            "wsgi.input": io.BytesIO(b"x" * 17),
        }
        BoundedUploadWSGI(application)(environ, Mock())
        application.assert_called_once()
        with self.assertRaises(RequestDataTooBig):
            environ["wsgi.input"].read()
