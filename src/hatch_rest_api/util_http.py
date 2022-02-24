import logging

from .util import clean_dictionary_for_logging

_LOGGER = logging.getLogger(__name__)


def request_with_logging(func):
    async def request_with_logging_wrapper(*args, **kwargs):
        url = kwargs["url"]
        request_message = f"sending {url} request"
        headers = kwargs.get("headers")
        if headers is not None:
            request_message = request_message + f"headers: {headers}"
        json_body = kwargs.get("json_body")
        if json_body is not None:
            request_message = (
                request_message
                + f"sending {url} request with {clean_dictionary_for_logging(json_body)}"
            )
        _LOGGER.debug(request_message)
        response = await func(*args, **kwargs)
        _LOGGER.debug(
            f"response headers:{clean_dictionary_for_logging(response.headers)}"
        )
        try:
            response_json = await response.json()
            _LOGGER.debug(
                f"response json: {clean_dictionary_for_logging(response_json)}"
            )
        except Exception:
            response_text = await response.text()
            _LOGGER.debug(f"response raw: {response_text}")
        return response

    return request_with_logging_wrapper
