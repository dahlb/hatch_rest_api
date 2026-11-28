"""Debug logs never contain credentials, tokens or account details.

Home Assistant users turn on debug logging and paste the output into GitHub
issues, so every request and response the library logs is checked here
through the real logging paths.
"""

import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aiohttp import ContentTypeError
import pytest

from hatch_rest_api import AwsHttp, Hatch
from hatch_rest_api.util import clean_for_logging
from hatch_rest_api.util_http import request_with_logging

from .test_util_bootstrap import _run_bootstrap

SECRETS = [
    "HATCH-LOGIN-TOKEN",
    "COGNITO-OPENID-TOKEN",
    "ACCESS-KEY-ID",
    "SECRET-KEY-VALUE",
    "SESSION-TOKEN-VALUE",
    "PASSWORD-VALUE",
    "person@example.com",
    "SESSION-COOKIE",
]


def _response(body: Any, json_ok: bool = True) -> MagicMock:
    """A response whose .json() works, or fails as it does for Cognito's content type."""
    response = MagicMock()
    response.status = 200
    response.headers = {"Content-Type": "application/json", "Set-Cookie": "SESSION-COOKIE"}
    if json_ok:
        response.json = AsyncMock(return_value=body)
    else:
        response.json = AsyncMock(side_effect=ContentTypeError(MagicMock(), ()))
    response.text = AsyncMock(return_value=json.dumps(body))
    response.read = AsyncMock(return_value=json.dumps(body).encode())
    return response


def _assert_no_secrets(caplog: pytest.LogCaptureFixture) -> None:
    logged = caplog.text
    assert logged, "expected debug output"
    leaked = [secret for secret in SECRETS if secret in logged]
    assert leaked == [], f"secrets in debug log: {leaked}"


async def test_hatch_login_token_and_member_are_redacted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Login credentials, the login token, the Cognito token and the account email are masked."""
    session = MagicMock()
    session.post = AsyncMock(
        return_value=_response({"status": "success", "token": "HATCH-LOGIN-TOKEN"})
    )
    session.get = AsyncMock(
        side_effect=[
            _response(
                {
                    "status": "success",
                    "payload": {
                        "token": "COGNITO-OPENID-TOKEN",
                        "identityId": "identity-1",
                        "region": "us-west-2",
                        "endpoint": "https://iot.example.invalid",
                    },
                }
            ),
            _response({"status": "success", "payload": {"email": "person@example.com", "id": 7}}),
        ]
    )
    api = Hatch(client_session=session)

    with caplog.at_level(logging.DEBUG):
        token = await api.login(email="person@example.com", password="PASSWORD-VALUE")
        aws_token = await api.token(auth_token=token)
        await api.member(auth_token=token)

    # The calls still return the real values; only the logs are masked.
    assert token == "HATCH-LOGIN-TOKEN"
    assert aws_token["token"] == "COGNITO-OPENID-TOKEN"
    _assert_no_secrets(caplog)
    # Non-secret context stays in the log.
    assert "identity-1" in caplog.text
    assert "us-west-2" in caplog.text


async def test_cognito_request_and_credentials_are_redacted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The OpenID token and AWS credentials are masked, even though .json() rejects the body."""
    credentials = {
        "IdentityId": "identity-1",
        "Credentials": {
            "AccessKeyId": "ACCESS-KEY-ID",
            "SecretKey": "SECRET-KEY-VALUE",
            "SessionToken": "SESSION-TOKEN-VALUE",
            "Expiration": 1780000000,
        },
    }
    session = MagicMock()
    session.post = AsyncMock(return_value=_response(credentials, json_ok=False))

    with caplog.at_level(logging.DEBUG):
        result = await AwsHttp(client_session=session).aws_credentials(
            region="us-west-2", identityId="identity-1", aws_token="COGNITO-OPENID-TOKEN"
        )

    assert result == credentials
    _assert_no_secrets(caplog)
    assert "1780000000" in caplog.text


def test_get_rest_devices_redacts_the_credentials_it_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """get_rest_devices logs the AWS credentials it received with the secrets masked."""
    with caplog.at_level(logging.DEBUG, logger="hatch_rest_api.util_bootstrap"):
        _run_bootstrap()

    credential_lines = [
        r.getMessage() for r in caplog.records if "AWS credentials" in r.getMessage()
    ]
    assert credential_lines, "expected the AWS credentials debug line"
    for line in credential_lines:
        # FakeAwsHttp in test_util_bootstrap returns these values.
        assert "'secret'" not in line
        assert "'session'" not in line
        assert "'key'" not in line
        assert "1780000000" in line


async def test_request_headers_are_redacted(caplog: pytest.LogCaptureFixture) -> None:
    """Auth headers passed to a logged request are masked."""

    @request_with_logging
    async def send(url: str, headers: dict[str, str]) -> MagicMock:
        return _response({"ok": True})

    with caplog.at_level(logging.DEBUG):
        await send(
            url="https://example.invalid",
            headers={
                "X-HatchBaby-Auth": "HATCH-LOGIN-TOKEN",
                "Authorization": "Bearer SECRET-KEY-VALUE",
            },
        )

    _assert_no_secrets(caplog)


async def test_non_json_bodies_are_still_logged(caplog: pytest.LogCaptureFixture) -> None:
    """A body that isn't JSON at all, such as an HTML error page, is logged as is."""
    response = _response({}, json_ok=False)
    response.text = AsyncMock(return_value="<html>Bad Gateway</html>")

    @request_with_logging
    async def send(url: str) -> MagicMock:
        return response

    with caplog.at_level(logging.DEBUG):
        await send(url="https://example.invalid")

    assert "<html>Bad Gateway</html>" in caplog.text


@pytest.mark.parametrize(
    "key",
    ["Token", "SecretKey", "SessionToken", "AccessKeyId", "Logins", "Email", "X-HatchBaby-Auth"],
)
def test_sensitive_keys_match_case_insensitively(key: str) -> None:
    """Sensitive keys are masked whatever their case, including inside lists."""
    assert clean_for_logging({key: "value"}) == {key: "***"}
    assert clean_for_logging({"items": [{key.lower(): "value"}]}) == {
        "items": [{key.lower(): "***"}]
    }
