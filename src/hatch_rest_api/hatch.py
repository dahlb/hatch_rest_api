import logging

from aiohttp import ClientSession, ClientResponse, ClientError, __version__
from aiohttp.hdrs import USER_AGENT

from .errors import AuthError
from .util_http import request_with_logging

_LOGGER = logging.getLogger(__name__)

API_URL: str = "https://data.hatchbaby.com/"


def request_with_logging_and_errors(func):
    async def request_with_logging_wrapper(*args, **kwargs):
        response = await func(*args, **kwargs)
        response_json = await response.json()
        if response_json.get("status") == "success":
            return response
        if response_json.get("errorCode") == 1001:
            _LOGGER.debug("error: session invalid")
            raise AuthError
        raise ClientError(f"api error:{response_json.get('message')}")

    return request_with_logging_wrapper


class Hatch:
    def __init__(self, client_session: ClientSession = None):
        if client_session is None:
            self.api_session = ClientSession(raise_for_status=True)
        else:
            self.api_session = client_session
        _LOGGER.debug(f"api_session_version: {__version__}")

    async def cleanup_client_session(self):
        await self.api_session.close()

    @request_with_logging_and_errors
    @request_with_logging
    async def _post_request_with_logging_and_errors_raised(
        self, url: str, json_body: dict, auth_token: str = None
    ) -> ClientResponse:
        headers = {USER_AGENT: "hatch_rest_api"}
        if auth_token is not None:
            headers["X-HatchBaby-Auth"] = auth_token
        return await self.api_session.post(url=url, json=json_body, headers=headers)

    @request_with_logging
    @request_with_logging_and_errors
    async def _get_request_with_logging_and_errors_raised(
        self, url: str, auth_token: str = None, params: dict = None
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
        response_json = await response.json()
        return response_json["token"]

    async def member(self, auth_token: str):
        url = API_URL + "service/app/v2/member"
        response: ClientResponse = (
            await self._get_request_with_logging_and_errors_raised(
                url=url, auth_token=auth_token
            )
        )
        response_json = await response.json()
        return response_json["payload"]

    async def iot_devices(self, auth_token: str):
        url = API_URL + "service/app/iotDevice/v2/fetch"
        params = {"iotProducts": ["restMini", "restPlus", "riot", "riotPlus", "restoreIot"]}
        response: ClientResponse = (
            await self._get_request_with_logging_and_errors_raised(
                url=url, auth_token=auth_token, params=params
            )
        )
        response_json = await response.json()
        return response_json["payload"]

    async def token(self, auth_token: str):
        url = API_URL + "service/app/restPlus/token/v1/fetch"
        response: ClientResponse = (
            await self._get_request_with_logging_and_errors_raised(
                url=url, auth_token=auth_token
            )
        )
        response_json = await response.json()
        return response_json["payload"]

    async def favorites(self, auth_token: str, mac: str):
        url = API_URL + "service/app/routine/v2/fetch"
        params = {"macAddress": mac, "types": "favorite"}
        response: ClientResponse = (
            await self._get_request_with_logging_and_errors_raised(
                url=url, auth_token=auth_token, params=params
            )
        )
        response_json = await response.json()
        favorites = response_json["payload"]
        favorites.sort(key=lambda x: x.get("displayOrder", float('inf')))
        return favorites

    async def content(self, auth_token: str, product: str, content: list):
        # content options are ["sound", "color", "windDown"]
        url = API_URL + "service/app/content/v1/fetchByProduct"
        params = {"product": product, "contentTypes": content}
        response: ClientResponse = (
            await self._get_request_with_logging_and_errors_raised(
                url=url, auth_token=auth_token, params=params
            )
        )
        response_json = await response.json()
        return response_json["payload"]
