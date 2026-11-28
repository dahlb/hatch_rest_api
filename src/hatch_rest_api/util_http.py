"""HTTP helpers shared by the API clients."""

import asyncio
from collections.abc import Awaitable, Callable
import json
import logging
from typing import Any

from aiohttp import ClientResponse

from .errors import RateError
from .util import clean_dictionary_for_logging, clean_for_logging

_LOGGER = logging.getLogger(__name__)

# Retries after a rate-limit response, waiting 2, 4 and 8 seconds.
DEFAULT_RATE_LIMIT_RETRIES = 3


async def retry_when_rate_limited[T](
    attempt: Callable[[], Awaitable[T]], max_retries: int, description: str
) -> T:
    """Await ``attempt()``, retrying with exponential backoff while it raises ``RateError``.

    Args:
        attempt: Makes one try of the request.
        max_retries: Retries after the first try; 0 raises the first ``RateError``.
        description: What is being requested, for the log.

    Returns:
        What ``attempt()`` returned.

    Raises:
        RateError: If still rate limited after ``max_retries`` retries.
    """
    retry_count = 0
    while True:
        try:
            return await attempt()
        except RateError:
            retry_count += 1
            if retry_count > max_retries:
                if max_retries:
                    _LOGGER.error("Maximum retries (%s) exceeded for %s", max_retries, description)
                raise
            wait_time = 2**retry_count
            _LOGGER.warning(
                "Rate limited on %s. Retrying in %s seconds (attempt %s/%s)",
                description,
                wait_time,
                retry_count,
                max_retries,
            )
            await asyncio.sleep(wait_time)


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
