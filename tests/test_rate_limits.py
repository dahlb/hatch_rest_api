"""Rate-limited Hatch and Contentful requests raise RateError and are retried with backoff.

These run against a real local aiohttp server, because whether a 429 reaches
the library's own check depends on the session's raise_for_status setting.
"""

from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer
import pytest

from hatch_rest_api import Hatch, RateError, contentful as contentful_module, hatch as hatch_module
from hatch_rest_api.contentful import Contentful

SUCCESS = {"status": "success", "payload": [{"id": 1}], "token": "t"}


class FakeHatchServer:
    """Answers 429 for the first ``rate_limited`` requests, then succeeds."""

    def __init__(self) -> None:
        """Start with no rate limiting."""
        self.rate_limited = 0
        self.requests = 0

    async def handle(self, request: web.Request) -> web.Response:
        """Answer one request."""
        self.requests += 1
        if self.requests <= self.rate_limited:
            return web.json_response({"message": "slow down"}, status=429)
        if request.path == "/graphql":
            return web.json_response({"data": {"ok": True}})
        return web.json_response(SUCCESS)


@pytest.fixture
async def server(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeHatchServer]:
    """A local server standing in for the Hatch and Contentful APIs."""
    fake = FakeHatchServer()
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", fake.handle)
    test_server = TestServer(app)
    await test_server.start_server()
    monkeypatch.setattr(hatch_module, "API_URL", str(test_server.make_url("/")))
    monkeypatch.setattr(contentful_module, "API_URL", str(test_server.make_url("/graphql")))
    yield fake
    await test_server.close()


@pytest.fixture
def sleep() -> Iterator[AsyncMock]:
    """Skip the backoff waits and record them."""
    with patch("hatch_rest_api.util_http.asyncio.sleep", new=AsyncMock()) as mock:
        yield mock


SESSIONS: dict[str, Callable[[], ClientSession | None]] = {
    # Hatch() makes its own session with raise_for_status=False.
    "hatch-own-session": lambda: None,
    "caller-session": ClientSession,
    "caller-session-raise-for-status": lambda: ClientSession(raise_for_status=True),
}


async def _hatch(session_kind: str, **kwargs: Any) -> Hatch:
    return Hatch(client_session=SESSIONS[session_kind](), **kwargs)


@pytest.mark.parametrize("session_kind", list(SESSIONS))
async def test_429_raises_rate_error(
    server: FakeHatchServer, sleep: AsyncMock, session_kind: str
) -> None:
    """A 429 raises RateError whatever the session's raise_for_status setting."""
    server.rate_limited = 100
    api = await _hatch(session_kind, rate_limit_retries=0)
    try:
        with pytest.raises(RateError):
            await api.iot_devices(auth_token="t")
    finally:
        await api.api_session.close()
    assert server.requests == 1
    sleep.assert_not_awaited()


@pytest.mark.parametrize("session_kind", list(SESSIONS))
async def test_rate_limited_get_is_retried(
    server: FakeHatchServer, sleep: AsyncMock, session_kind: str
) -> None:
    """A GET is retried after 2s and 4s waits and then succeeds."""
    server.rate_limited = 2
    api = await _hatch(session_kind)
    try:
        devices = await api.iot_devices(auth_token="t")
    finally:
        await api.api_session.close()
    assert devices == [{"id": 1}]
    assert server.requests == 3
    assert [call.args[0] for call in sleep.await_args_list] == [2, 4]


async def test_rate_limited_post_is_retried(server: FakeHatchServer, sleep: AsyncMock) -> None:
    """A POST, such as login, is retried too."""
    server.rate_limited = 1
    api = await _hatch("hatch-own-session")
    try:
        assert await api.login(email="a@example.invalid", password="pw") == "t"
    finally:
        await api.api_session.close()
    assert server.requests == 2


async def test_gives_up_after_rate_limit_retries(server: FakeHatchServer, sleep: AsyncMock) -> None:
    """After rate_limit_retries retries, RateError is raised."""
    server.rate_limited = 100
    api = await _hatch("hatch-own-session", rate_limit_retries=2)
    try:
        with pytest.raises(RateError):
            await api.member(auth_token="t")
    finally:
        await api.api_session.close()
    assert server.requests == 3
    assert [call.args[0] for call in sleep.await_args_list] == [2, 4]


async def test_content_max_retries_overrides_the_client(
    server: FakeHatchServer, sleep: AsyncMock
) -> None:
    """content(max_retries=...) still sets the retries for that call, without retrying twice."""
    server.rate_limited = 100
    api = await _hatch("hatch-own-session", rate_limit_retries=5)
    try:
        with pytest.raises(RateError):
            await api.content(auth_token="t", product="riot", content=["sound"], max_retries=1)
    finally:
        await api.api_session.close()
    assert server.requests == 2


@pytest.mark.parametrize("raise_for_status", [False, True])
async def test_contentful_rate_limit(
    server: FakeHatchServer, sleep: AsyncMock, raise_for_status: bool
) -> None:
    """Contentful retries a 429 and raises RateError when it runs out, either session kind."""
    server.rate_limited = 1
    async with ClientSession(raise_for_status=raise_for_status) as session:
        assert await Contentful(client_session=session).graphql_query("query Q { x }") == {
            "ok": True
        }
        server.requests, server.rate_limited = 0, 100
        with pytest.raises(RateError):
            await Contentful(client_session=session, rate_limit_retries=0).graphql_query("q")
    assert server.requests == 1
