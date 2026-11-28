"""HTTP helpers shared by the API clients."""

from collections.abc import Awaitable, Callable
import json
import logging
from typing import Any

from aiohttp import ClientResponse

from .util import clean_dictionary_for_logging, clean_for_logging

_LOGGER = logging.getLogger(__name__)


def request_with_logging(
    func: Callable[..., Awaitable[ClientResponse]],
) -> Callable[..., Awaitable[ClientResponse]]:
    """Wrap an HTTP request coroutine with debug logging of request and response.

    Args:
        func: Coroutine that performs the request and returns the response.

    Returns:
        The wrapped coroutine.
    """

    async def request_with_logging_wrapper(*args: Any, **kwargs: Any) -> ClientResponse:
        url = kwargs["url"]
        request_message = f"sending {url} request"
        headers = kwargs.get("headers")
        if headers is not None:
            request_message = request_message + f"headers: {clean_for_logging(headers)}"
        json_body = kwargs.get("json_body")
        if json_body is not None:
            request_message = (
                request_message + f"sending {url} request with {clean_for_logging(json_body)}"
            )
        _LOGGER.debug(request_message)
        response = await func(*args, **kwargs)
        _LOGGER.debug("response headers:%s", clean_dictionary_for_logging(response.headers))
        try:
            response_json = await response.json()
            _LOGGER.debug("response json: %s", clean_dictionary_for_logging(response_json))
        except Exception:  # noqa: BLE001 - log raw body for any decode failure
            response_text = await response.text()
            # Cognito answers with application/x-amz-json-1.1, which response.json()
            # rejects, so parse it here to redact the credentials it carries.
            try:
                _LOGGER.debug("response json: %s", clean_for_logging(json.loads(response_text)))
            except ValueError:
                _LOGGER.debug("response raw: %s", response_text)
        return response

    return request_with_logging_wrapper
