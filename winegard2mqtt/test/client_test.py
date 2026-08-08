"""Client tests run against a real local HTTP server, not mocks.

The behaviour that matters here is the LuCI session handshake: a form login
that returns a cookie, and recovery when that cookie expires an hour later.
Mocking the transport would test the mock, not that handshake.
"""

import json
import pathlib
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from winegard2mqtt.client import AuthError, WinegardClient

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SYS_STATUS = (FIXTURES / "sys_status_nofix.json").read_text()
LOGIN_PAGE = (FIXTURES / "login_page.html").read_text()

LOGIN_PATH = "/cgi-bin/luci/themes/winegard2/index.htm"
STATUS_PATH = "/cgi-bin/luci/sys_status"


class FakeRouter:
    """Stands in for the ConnecT's LuCI interface."""

    def __init__(self, password="admin"):
        self.password = password
        self.valid_cookie = None
        self.login_count = 0
        self.status_requests = 0
        self.expire_next_status = False
        self._counter = 0

    def issue_cookie(self):
        self._counter += 1
        self.valid_cookie = f"sess{self._counter}"
        return self.valid_cookie


def _handler_for(router):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body, headers=()):
            payload = body.encode()
            self.send_response(code)
            for key, value in headers:
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            router.login_count += 1
            if f"luci_password={router.password}" not in body:
                self._send(403, LOGIN_PAGE)
                return
            cookie = router.issue_cookie()
            self._send(302, "", [
                ("Set-Cookie", f"{'sysauth2'}={cookie}; path=/cgi-bin/luci/; Max-Age=3600"),
                ("Location", LOGIN_PATH),
            ])

        def do_GET(self):
            if not self.path.startswith(STATUS_PATH):
                self._send(404, "")
                return
            router.status_requests += 1
            cookie = self.headers.get("Cookie", "")
            authorised = router.valid_cookie and router.valid_cookie in cookie
            if router.expire_next_status:
                router.expire_next_status = False
                router.valid_cookie = None
                authorised = False
            if not authorised:
                self._send(403, LOGIN_PAGE)
                return
            self._send(200, SYS_STATUS, [("Content-Type", "application/json")])

    return Handler


@pytest.fixture
def router():
    return FakeRouter()


@pytest.fixture
def client(router):
    server = HTTPServer(("127.0.0.1", 0), _handler_for(router))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield WinegardClient(f"http://{host}:{port}", "admin", "admin")
    server.shutdown()
    server.server_close()


def test_status_is_fetched_after_logging_in(client, router):
    status = client.status()
    assert status["gps"]["tracking"] is True
    assert router.login_count == 1


def test_session_is_reused_across_polls(client, router):
    client.status()
    client.status()
    client.status()
    assert router.login_count == 1, "should not re-authenticate while the cookie is valid"
    assert router.status_requests == 3


def test_expired_session_triggers_relogin_and_retry(client, router):
    client.status()
    router.expire_next_status = True

    status = client.status()

    assert status["gps"]["tracking"] is True, "poll should succeed despite expiry"
    assert router.login_count == 2, "should have re-authenticated exactly once"


def test_wrong_password_raises_auth_error(router):
    router.password = "something-else"
    server = HTTPServer(("127.0.0.1", 0), _handler_for(router))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address
    bad = WinegardClient(f"http://{host}:{port}", "admin", "admin")

    with pytest.raises(AuthError):
        bad.status()

    server.shutdown()
    server.server_close()
