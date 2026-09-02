"""Entrypoint for running the procrastinate worker on Cloud Run.

Cloud Run requires every container to listen on $PORT for health checks. The
procrastinate worker doesn't serve HTTP, so we run both:

  - the worker (blocking, main thread): `python manage.py procrastinate worker --queues=default,builtin`
  - a tiny HTTP listener on $PORT in a daemon thread: responds 200 to anything

If the worker process crashes, the entrypoint exits non-zero so Cloud Run
schedules a replacement instance. Deploy with:

    --command=python
    --args=ledova_backend/worker_entrypoint.py
    --no-cpu-throttling
    --min-instances=1
"""

import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *_):
        pass


def _serve_health(port: int) -> None:
    HTTPServer(("0.0.0.0", port), _Health).serve_forever()


def main() -> int:
    port = int(os.environ.get("PORT", "8080"))
    threading.Thread(target=_serve_health, args=(port,), daemon=True).start()

    # Blocks until worker exits.
    result = subprocess.run(
        [sys.executable, "manage.py", "procrastinate", "worker", "--queues=default,builtin"],
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
