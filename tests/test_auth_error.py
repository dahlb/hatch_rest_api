import asyncio
import unittest

from aiohttp import ClientError

from hatch_rest_api.errors import AuthError
from hatch_rest_api.hatch import Hatch


class FakeResponse:
    status = 200
    headers = {}

    def __init__(self, url: str, payload: dict):
        self.url = url
        self._payload = payload

    async def json(self):
        return self._payload

    async def text(self):
        return str(self._payload)


class FakeSession:
    def __init__(self, payload: dict):
        self.payload = payload

    async def post(self, url: str, json: dict, headers: dict):
        return FakeResponse(url, self.payload)


def login_failure(error_code) -> dict:
    return {
        "errorCode": error_code,
        "message": "Login failed for [user@example.com]",
        "payload": None,
        "status": "failure",
        "sync": None,
    }


class AuthErrorTest(unittest.TestCase):
    def _login(self, payload: dict):
        api = Hatch(client_session=FakeSession(payload))
        return asyncio.run(api.login(email="user@example.com", password="bad"))

    def test_string_error_code_raises_auth_error(self):
        # This is what the live API returns for bad credentials.
        with self.assertRaises(AuthError):
            self._login(login_failure("1001"))

    def test_int_error_code_raises_auth_error(self):
        with self.assertRaises(AuthError):
            self._login(login_failure(1001))

    def test_other_error_code_is_not_auth_error(self):
        with self.assertRaises(ClientError) as ctx:
            self._login(login_failure("2000"))
        self.assertNotIsInstance(ctx.exception, AuthError)


if __name__ == "__main__":
    unittest.main()
