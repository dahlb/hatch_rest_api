import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
import logging
from typing import Literal, TypedDict, overload

from aiohttp import ClientError, ClientResponse, ClientSession, __version__
from aiohttp.hdrs import USER_AGENT

from .errors import AuthError, RateError
from .types import (
    IotDeviceInfo,
    IotTokenResponse,
    JsonType,
    LoginResponse,
    Product,
    RestIotRoutine,
    SimpleSoundContent,
)
from .util_http import request_with_logging

type ContentType = Literal["sound", "color", "windDown"]


class ContentResponse[T: SimpleSoundContent | Mapping[str, JsonType]](TypedDict):
    contentItems: list[T]


_LOGGER = logging.getLogger(__name__)

API_URL: str = "https://data.hatchbaby.com/"


def request_with_logging_and_errors[**P, T: ClientResponse](
    func: Callable[P, Awaitable[T]],
) -> Callable[P, Awaitable[T]]:
    async def request_with_logging_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        response = await func(*args, **kwargs)

        if response.status == 429:
            _LOGGER.warning(f"Rate limited (429) for URL: {response.url}")
            raise RateError("API rate limit exceeded. Please wait before retrying.")

        try:
            response_json = await response.json()
        except Exception:
            try:
                response_text = await response.text()
                _LOGGER.error(
                    f"Failed to parse JSON response. Status: {response.status}, Content: {response_text[:500]}"
                )
            except Exception:
                _LOGGER.error(f"Failed to parse response. Status: {response.status}")
            raise ClientError(
                f"Invalid response format from API (status: {response.status})"
            )

        if response_json.get("status") == "success":
            return response
        if response_json.get("errorCode") == 1001:
            _LOGGER.debug("error: session invalid")
            raise AuthError
        raise ClientError(f"api error:{response_json.get('message')}")

    return request_with_logging_wrapper


class Hatch:
    def __init__(self, client_session: ClientSession | None = None):
        if client_session is None:
            self.api_session = ClientSession(raise_for_status=True)
        else:
            self.api_session = client_session
        _LOGGER.debug(f"api_session_version: {__version__}")

    async def cleanup_client_session(self) -> None:
        await self.api_session.close()

    @request_with_logging_and_errors
    @request_with_logging
    async def _post_request_with_logging_and_errors_raised(
        self, url: str, json_body: dict, auth_token: str | None = None
    ) -> ClientResponse:
        headers = {USER_AGENT: "hatch_rest_api"}
        if auth_token is not None:
            headers["X-HatchBaby-Auth"] = auth_token
        return await self.api_session.post(url=url, json=json_body, headers=headers)

    @request_with_logging
    @request_with_logging_and_errors
    async def _get_request_with_logging_and_errors_raised(
        self, url: str, auth_token: str | None = None, params: dict | None = None
    ) -> ClientResponse:
        headers = {USER_AGENT: "hatch_rest_api"}
        if auth_token is not None:
            headers["X-HatchBaby-Auth"] = auth_token
        return await self.api_session.get(url=url, headers=headers, params=params)

    async def login(self, email: str, password: str) -> str:
        url = API_URL + "public/v1/login"
        json_body = {
            "email": email,
            "password": password,
        }
        response: ClientResponse = (
            await self._post_request_with_logging_and_errors_raised(
                url=url, json_body=json_body
            )
        )
        response_json: LoginResponse = await response.json()
        return response_json["token"]

    async def member(self, auth_token: str) -> dict[str, JsonType]:
        url = API_URL + "service/app/v2/member"
        response: ClientResponse = (
            await self._get_request_with_logging_and_errors_raised(
                url=url, auth_token=auth_token
            )
        )
        response_json = await response.json()
        return response_json["payload"]

    async def iot_devices(self, auth_token: str) -> list[IotDeviceInfo]:
        url = API_URL + "service/app/iotDevice/v2/fetch"
        params = {
            "iotProducts": [
                "restMini",
                "restPlus",
                "riot",
                "riotPlus",
                "restoreIot",
                "restoreV5",
            ]
        }
        response: ClientResponse = (
            await self._get_request_with_logging_and_errors_raised(
                url=url, auth_token=auth_token, params=params
            )
        )
        response_json = await response.json()
        return response_json["payload"]

    async def token(self, auth_token: str) -> IotTokenResponse:
        url = API_URL + "service/app/restPlus/token/v1/fetch"
        response: ClientResponse = (
            await self._get_request_with_logging_and_errors_raised(
                url=url, auth_token=auth_token
            )
        )
        response_json = await response.json()
        return response_json["payload"]

    async def favorites(self, auth_token: str, mac: str) -> list[RestIotRoutine]:
        url = API_URL + "service/app/routine/v2/fetch"
        params = {"macAddress": mac}
        response: ClientResponse = (
            await self._get_request_with_logging_and_errors_raised(
                url=url, auth_token=auth_token, params=params
            )
        )
        response_json = await response.json()
        favorites: list[RestIotRoutine] = response_json["payload"]
        favorites.sort(key=lambda x: x.get("displayOrder", float("inf")))
        return favorites

    async def routines(self, auth_token: str, mac: str) -> list[RestIotRoutine]:
        url = API_URL + "service/app/routine/v2/fetch"
        params = {"macAddress": mac, "types": "routine"}
        response: ClientResponse = (
            await self._get_request_with_logging_and_errors_raised(
                url=url, auth_token=auth_token, params=params
            )
        )
        response_json = await response.json()
        routines: list[RestIotRoutine] = response_json["payload"]
        routines.sort(key=lambda x: x.get("displayOrder", float("inf")))
        return routines

    @overload
    async def content(
        self,
        auth_token: str,
        product: Product,
        content: Sequence[Literal["sound"]],
        max_retries: int = 3,
    ) -> ContentResponse[SimpleSoundContent]: ...
    @overload
    async def content(
        self,
        auth_token: str,
        product: Product,
        content: Sequence[Literal["color", "windDown"]],
        max_retries: int = 3,
    ) -> ContentResponse[Mapping[str, JsonType]]: ...
    async def content(
        self,
        auth_token: str,
        product: Product,
        content: Sequence[ContentType],
        max_retries: int = 3,
    ) -> ContentResponse[Mapping[str, JsonType]] | ContentResponse[SimpleSoundContent]:
        # content options are ["sound", "color", "windDown"]
        url = API_URL + "service/app/content/v1/fetchByProduct"
        params = {"product": product, "contentTypes": content}

        retry_count = 0
        while True:
            try:
                response: ClientResponse = (
                    await self._get_request_with_logging_and_errors_raised(
                        url=url, auth_token=auth_token, params=params
                    )
                )
                response_json = await response.json()
                return response_json["payload"]
            except RateError:
                retry_count += 1
                if retry_count > max_retries:
                    _LOGGER.error(
                        f"Maximum retries ({max_retries}) exceeded for content API call"
                    )
                    raise

                # Calculate exponential backoff wait time (2^retry_count seconds)
                wait_time = 2**retry_count
                _LOGGER.warning(
                    f"Rate limited. Retrying in {wait_time} seconds (attempt {retry_count}/{max_retries})"
                )
                await asyncio.sleep(wait_time)
