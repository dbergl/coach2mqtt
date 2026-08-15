"""HTTP client for the Winegard ConnecT's LuCI interface.

Authentication is LuCI's form login, not ubus: the device's ``/ubus`` endpoint
exists but ``session.login`` returns permission denied, because Winegard locked
down the rpcd user database.

The session cookie carries ``Max-Age=3600``, so any long-running poller will
outlive it. Expiry shows up as a 403 (or as the login page served in place of
the content), and is recovered by logging in again and retrying once.
"""

import logging
from typing import Optional

import requests

LOGIN_PATH = "/cgi-bin/luci/themes/winegard2/index.htm"
STATUS_PATH = "/cgi-bin/luci/sys_status"

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Credentials were rejected by the router."""


class WinegardClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self._session: Optional[requests.Session] = None

    # -- internals ----------------------------------------------------------

    def _login(self) -> requests.Session:
        session = requests.Session()
        response = session.post(
            self.base_url + LOGIN_PATH,
            data={
                "luci_username": self.username,
                "luci_password": self.password,
                "luci_continue": "CONTINUE",
            },
            timeout=self.timeout,
            allow_redirects=False,
        )
        if not any(name.startswith("sysauth") for name in session.cookies.keys()):
            raise AuthError(
                f"login rejected by {self.base_url} (HTTP {response.status_code}); "
                "check WINEGARD_PASSWORD"
            )
        self._session = session
        return session

    def _get(self, path: str) -> requests.Response:
        """GET with one re-login retry if the session has expired."""
        session = self._session or self._login()
        response = session.get(self.base_url + path, timeout=self.timeout)
        if self._is_expired(response):
            logger.info("session expired, re-authenticating")
            session = self._login()
            response = session.get(self.base_url + path, timeout=self.timeout)
            if self._is_expired(response):
                raise AuthError("still unauthorised after re-authenticating")
        response.raise_for_status()
        return response

    @staticmethod
    def _is_expired(response: requests.Response) -> bool:
        if response.status_code == 403:
            return True
        # A valid-looking 200 that is actually the login form.
        return "luci_password" in response.text[:4096]

    # -- public API ---------------------------------------------------------

    def status(self) -> dict:
        """Fetch and decode ``sys_status``.

        The only endpoint this bridge needs: the GPS Services page renders the
        same values with units glued on and omits the quality fields, so there
        is nothing to fetch from it.
        """
        return self._get(STATUS_PATH).json()
