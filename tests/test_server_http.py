"""The HTTP adapter serves the console over a real socket."""

import json
import threading
import urllib.error
import urllib.request

from paperops.config import Config
from paperops.console.server import ControlServer

from support import WEB_DIR, build


def request(port: int, method: str, path: str, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    call = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, method=method
    )
    with urllib.request.urlopen(call, timeout=5) as response:
        return response.status, json.loads(response.read())


def test_http_server_serves_health_api_and_pages(tmp_path):
    services = build(Config(data_dir=str(tmp_path / "data"), web_dir=WEB_DIR))
    server = ControlServer(("127.0.0.1", 0), services.console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        status, payload = request(port, "GET", "/healthz")
        assert status == 200
        assert payload["status"] == "ok"

        assert request(port, "POST", "/api/steam/drain", {})[0] == 200
        status, payload = request(port, "POST", "/api/steam/valve", {"open": True})
        assert status == 200
        assert payload["valve_open"] is True

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
            assert response.status == 200
            assert "总览" in response.read().decode("utf-8")

        try:
            request(port, "POST", "/api/reel/retract", {})
            raised = False
        except urllib.error.HTTPError as error:
            raised = True
            assert error.code == 409
        assert raised
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
