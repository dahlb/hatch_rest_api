"""Tests for mapping Hatch login failures to AuthError."""

import asyncio
from typing import Any, ClassVar
import unittest

from aiohttp import ClientError
import pytest

from hatch_rest_api.errors import AuthError
from hatch_rest_api.hatch import Hatch


class FakeResponse:
    """Stand-in for an aiohttp response with a fixed JSON payload."""

    status = 200
    headers: ClassVar[dict[str, str]] = {}

    def __init__(self, url: str, payload: dict[str, Any]) -> None:
        """Store the request URL and the payload to return."""
        self.url = url
        self._payload = payload

    async def json(self) -> dict[str, Any]:
        """Return the payload."""
        return self._payload

    async def text(self) -> str:
        """Return the payload as text."""
        return str(self._payload)


class FakeSession:
    """Stand-in for an aiohttp session that answers every POST with one payload."""

    def __init__(self, payload: dict[str, Any]) -> None:
        """Store the payload to return."""
        self.payload = payload

    async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
        """Return the stored payload."""
        return FakeResponse(url, self.payload)


def login_failure(error_code: str | int) -> dict[str, Any]:
    """Build a failed login response with ``error_code``."""
    return {
        "errorCode": error_code,
        "message": "Login failed for [user@example.com]",
        "payload": None,
        "status": "failure",
        "sync": None,
    }


class AuthErrorTest(unittest.TestCase):
    """Login failures raise the right error types."""

    def _login(self, payload: dict[str, Any]) -> str:
        api = Hatch(client_session=FakeSession(payload))
        return asyncio.run(api.login(email="user@example.com", password="bad"))

    def test_string_error_code_raises_auth_error(self) -> None:
        """String error code raises auth error."""
        # This is what the live API returns for bad credentials.
        with pytest.raises(AuthError):
            self._login(login_failure("1001"))

    def test_int_error_code_raises_auth_error(self) -> None:
        """Int error code raises auth error."""
        with pytest.raises(AuthError):
            self._login(login_failure(1001))

    def test_other_error_code_is_not_auth_error(self) -> None:
        """Other error code is not auth error."""
        with pytest.raises(ClientError) as ctx:
            self._login(login_failure("2000"))
        assert not isinstance(ctx.value, AuthError)


if __name__ == "__main__":
    unittest.main()
