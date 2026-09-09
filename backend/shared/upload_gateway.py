import asyncio
import json
import time

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.core.handlers.asgi import get_script_prefix
from django.urls import Resolver404, resolve


def is_upload_request(path, method):
    if method.upper() != "POST":
        return False
    try:
        callback = resolve(path).func
    except Resolver404:
        return False
    return (
        hasattr(getattr(callback, "cls", None), "upload_field")
        and getattr(callback, "actions", {}).get("post") == "create"
    )


def refused_body(status):
    detail = "The upload request timed out." if status == 408 else "The upload request is too large."
    return json.dumps({"detail": detail}).encode()


def declared_size_is_allowed(value):
    try:
        return 0 <= int(value or 0) <= settings.UPLOAD_MAX_REQUEST_BYTES
    except (TypeError, ValueError):
        return False


def asgi_path_info(scope):
    path = scope["path"]
    prefix = get_script_prefix(scope).rstrip("/")
    if prefix and (path == prefix or path.startswith(prefix + "/")):
        return path[len(prefix) :]
    return path


class BoundedUploadASGI:
    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not is_upload_request(asgi_path_info(scope), scope["method"]):
            return await self.application(scope, receive, send)
        headers = dict(scope.get("headers", []))
        rejected = None if declared_size_is_allowed(headers.get(b"content-length")) else 413
        received = 0
        body_finished = False
        deadline = time.monotonic() + settings.UPLOAD_BODY_SECONDS

        async def bounded_receive():
            nonlocal received, rejected, body_finished
            if body_finished:
                return await receive()
            try:
                message = await asyncio.wait_for(receive(), max(0, deadline - time.monotonic()))
            except TimeoutError:
                rejected = 408
                return {"type": "http.disconnect"}
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > settings.UPLOAD_MAX_REQUEST_BYTES:
                    rejected = 413
                    return {"type": "http.disconnect"}
                body_finished = not message.get("more_body", False)
            return message

        if rejected is None:
            await self.application(scope, bounded_receive, send)
        if rejected is not None:
            body = refused_body(rejected)
            await send(
                {
                    "type": "http.response.start",
                    "status": rejected,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
                }
            )
            await send({"type": "http.response.body", "body": body})


class BoundedUploadInput:
    def __init__(self, stream):
        self.stream = stream
        self.received = 0

    def _read(self, method, size):
        remaining = settings.UPLOAD_MAX_REQUEST_BYTES + 1 - self.received
        requested = remaining if size is None or size < 0 else min(size, remaining)
        data = getattr(self.stream, method)(requested)
        self.received += len(data)
        if self.received > settings.UPLOAD_MAX_REQUEST_BYTES:
            raise RequestDataTooBig("The upload request is too large.")
        return data

    def read(self, size=-1):
        return self._read("read", size)

    def readline(self, size=-1):
        return self._read("readline", size)

    def readlines(self, hint=-1):
        lines = []
        total = 0
        for line in self:
            lines.append(line)
            total += len(line)
            if 0 < hint <= total:
                break
        return lines

    def __iter__(self):
        return self

    def __next__(self):
        line = self.readline()
        if not line:
            raise StopIteration()
        return line


class BoundedUploadWSGI:
    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        if is_upload_request(environ.get("PATH_INFO", ""), environ.get("REQUEST_METHOD", "GET")):
            if not declared_size_is_allowed(environ.get("CONTENT_LENGTH")):
                body = refused_body(413)
                start_response(
                    "413 Content Too Large", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))]
                )
                return [body]
            environ["wsgi.input"] = BoundedUploadInput(environ["wsgi.input"])
        return self.application(environ, start_response)
