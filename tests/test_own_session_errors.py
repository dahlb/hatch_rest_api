"""Errors through the sessions Hatch and AwsHttp create themselves (raise_for_status=False).

Every non-2xx response reaches the library's own handling and is logged, instead of
aiohttp raising a bare ClientResponseError first. Runs against a real local server.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
import logging
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientResponseError, web
from aiohttp.test_utils import TestServer
import pytest

from hatch_rest_api import AuthError, AwsHttp, Hatch


def _answer(response: web.Response) -> Callable[[web.Request], Awaitable[web.Response]]:
    async def handler(request: web.Request) -> web.Response:
        return response

    return handler


ROUTES = {
    "/auth": web.json_response(
        {"status": "error", "errorCode": "1001", "message": "session invalid"}, status=401
    ),
    "/api-error": web.json_response({"status": "error", "message": "device not found"}, status=404),
    "/html": web.Response(text="<html>Bad Gateway</html>", status=502),
    "/": web.json_response(
        {"__type": "NotAuthorizedException", "message": "Invalid login token"}, status=400
    ),
}


@pytest.fixture
async def server() -> AsyncIterator[TestServer]:
    """A local server answering each route with an error."""
    app = web.Application()
    for path, handler in ROUTES.items():
        app.router.add_route("*", path, _answer(handler))
    test_server = TestServer(app)
    await test_server.start_server()
    yield test_server
    await test_server.close()


async def _get(server: TestServer, path: str) -> None:
    api = Hatch()
    try:
        await api._get_request_with_logging_and_errors_raised(url=str(server.make_url(path)))
    finally:
        await api.api_session.close()


async def test_own_session_does_not_raise_for_status() -> None:
    """Hatch and AwsHttp create their sessions with raise_for_status=False."""
    hatch, aws = Hatch(), AwsHttp()
    try:
        assert hatch.api_session._raise_for_status is False
        assert aws.api_session._raise_for_status is False
    finally:
        await hatch.api_session.close()
        await aws.api_session.close()


async def test_session_invalid_raises_auth_error(server: TestServer) -> None:
    """A 401 carrying Hatch's session-invalid code raises AuthError, not ClientResponseError."""
    with pytest.raises(AuthError):
        await _get(server, "/auth")


async def test_api_error_raises_client_error_with_its_message(
    server: TestServer, caplog: pytest.LogCaptureFixture
) -> None:
    """An error response raises ClientError with the API's message, after logging it."""
    with caplog.at_level(logging.DEBUG), pytest.raises(ClientError, match="device not found"):
        await _get(server, "/api-error")
    assert "device not found" in caplog.text


async def test_non_json_error_raises_client_error(server: TestServer) -> None:
    """A non-JSON error page raises ClientError."""
    with pytest.raises(ClientError, match="Invalid response format"):
        await _get(server, "/html")


async def test_aws_credentials_error_still_raises(
    server: TestServer, caplog: pytest.LogCaptureFixture
) -> None:
    """A Cognito error still raises ClientResponseError, and its body is logged first."""
    aws = AwsHttp()
    post = aws._post_request_with_logging_and_errors_raised

    async def post_to_local_server(url: str, **kwargs: Any) -> ClientResponse:
        # aws_credentials builds the real Cognito URL; send it here instead.
        return await post(url=str(server.make_url("/")), **kwargs)

    aws._post_request_with_logging_and_errors_raised = post_to_local_server  # type: ignore[method-assign]
    try:
        with caplog.at_level(logging.DEBUG), pytest.raises(ClientResponseError) as raised:
            await aws.aws_credentials(region="us-west-2", identityId="id", aws_token="token")
    finally:
        await aws.api_session.close()
    assert raised.value.status == 400
    assert "Invalid login token" in caplog.text
