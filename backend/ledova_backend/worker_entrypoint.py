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

    result = subprocess.run(
        [sys.executable, "manage.py", "procrastinate", "worker", "--queues=default,builtin"],
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
