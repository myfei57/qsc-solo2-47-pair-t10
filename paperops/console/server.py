"""HTTP adapter around the console router."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from ..config import Config
from .http import Request
from .router import Console


class ControlHandler(BaseHTTPRequestHandler):
    """Translates HTTP requests into console requests."""

    server_version = "control-console/1.0"

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        response = self.server.console.handle(Request.parse(method, self.path, body))
        payload = response.to_bytes()
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: Any) -> None:
        """Stay quiet; the event record is the audit trail."""


class ControlServer(ThreadingHTTPServer):
    """HTTP server that carries the console router."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], console: Console) -> None:
        super().__init__(address, ControlHandler)
        self.console = console


def serve(config: Config, console: Console) -> None:
    """Serve the console until the process is stopped."""
    server = ControlServer(config.listen(), console)
    try:
        server.serve_forever()
    finally:
        server.server_close()
