"""Hatch logs a response before raising for it, for GET as well as POST."""

import logging
from unittest.mock import AsyncMock, MagicMock

from aiohttp import ClientError
import pytest

from hatch_rest_api import Hatch


def _error_response() -> MagicMock:
    response = MagicMock()
    response.status = 200
    response.headers = {}
    response.json = AsyncMock(return_value={"status": "error", "message": "device not found"})
    return response


async def test_failed_get_response_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """A GET that returns an API error is logged before ClientError is raised."""
    session = MagicMock()
    session.get = AsyncMock(return_value=_error_response())

    with caplog.at_level(logging.DEBUG), pytest.raises(ClientError, match="device not found"):
        await Hatch(client_session=session).iot_devices(auth_token="token")

    assert "device not found" in caplog.text


async def test_failed_post_response_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """A POST that returns an API error is logged before ClientError is raised."""
    session = MagicMock()
    session.post = AsyncMock(return_value=_error_response())

    with caplog.at_level(logging.DEBUG), pytest.raises(ClientError, match="device not found"):
        await Hatch(client_session=session).login(email="a@example.invalid", password="pw")

    assert "device not found" in caplog.text
