import asyncio
import logging
from collections.abc import Iterable
from datetime import time
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession, __version__
from aiohttp.hdrs import USER_AGENT

from .errors import AuthError, RateError
from .scheduled_routine import (
    ALARM_ROUTINE_TYPE,
    ScheduledRoutineAlarm,
    alarm_routines,
    alarm_update_payload,
    alarm_weekdays_update_payload,
    alarm_wake_time_update_payload,
)
from .util_http import request_with_logging

_LOGGER = logging.getLogger(__name__)

API_URL: str = "https://data.hatchbaby.com/"


def request_with_logging_and_errors(func):
    async def request_with_logging_wrapper(*args, **kwargs):
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
        params = {
            "iotProducts": [
                "restMini",
                "restPlus",
                "riot",
                "riotPlus",
                "restBaby",
                "restoreIot",
                "restoreV4",
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
        params = {"macAddress": mac}
        response: ClientResponse = (
            await self._get_request_with_logging_and_errors_raised(
                url=url, auth_token=auth_token, params=params
            )
        )
        response_json = await response.json()
        favorites = response_json["payload"]
        favorites.sort(key=lambda x: x.get("displayOrder", float("inf")))
        return favorites

    async def routines(self, auth_token: str, mac: str):
        url = API_URL + "service/app/routine/v2/fetch"
        params = {"macAddress": mac, "types": "routine"}
        response: ClientResponse = (
            await self._get_request_with_logging_and_errors_raised(
                url=url, auth_token=auth_token, params=params
            )
        )
        response_json = await response.json()
        routines = response_json["payload"]
        routines.sort(key=lambda x: x.get("displayOrder", float("inf")))
        return routines

    async def scheduled_routines(
        self,
        auth_token: str,
        mac: str,
        types: list[str] | None = None,
    ) -> list[ScheduledRoutineAlarm]:
        url = API_URL + "service/app/routine/v3/fetch"
        params: dict[str, str | list[str]] = {"macAddress": mac}
        if types is not None:
            params["types"] = types
        response: ClientResponse = (
            await self._get_request_with_logging_and_errors_raised(
                url=url, auth_token=auth_token, params=params
            )
        )
        response_json = await response.json()
        routines = response_json["payload"]
        routines.sort(key=lambda x: x.get("displayOrder", float("inf")))
        return routines

    async def update_scheduled_routine_alarm_enabled(
        self,
        auth_token: str,
        mac: str,
        alarm: ScheduledRoutineAlarm,
        enabled: bool,
    ) -> list[ScheduledRoutineAlarm]:
        payload = await self.edit_scheduled_routines(
            auth_token=auth_token,
            mutable_scheduled_routines=[alarm_update_payload(alarm, enabled)],
            routine_type=ALARM_ROUTINE_TYPE,
        )
        updated_routines = alarm_routines(payload.get("item") or [])

        if payload.get("confirmDataVersion") and payload.get("dataVersion"):
            try:
                confirmed_routines = await self.confirm_data_version(
                    auth_token=auth_token,
                    mac=mac,
                    data_version=payload["dataVersion"],
                    success=True,
                    return_all_routines=True,
                )
                if confirmed_routines:
                    updated_routines = alarm_routines(confirmed_routines)
            except ClientError as error:
                _LOGGER.warning(
                    "Could not confirm scheduled routine data version for %s",
                    mac,
                    exc_info=error,
                )

        return updated_routines

    async def update_scheduled_routine_alarm_wake_time(
        self,
        auth_token: str,
        mac: str,
        alarm: ScheduledRoutineAlarm,
        wake_time: time,
    ) -> list[ScheduledRoutineAlarm]:
        payload = await self.edit_scheduled_routines(
            auth_token=auth_token,
            mutable_scheduled_routines=[
                alarm_wake_time_update_payload(alarm, wake_time)
            ],
            routine_type=ALARM_ROUTINE_TYPE,
        )
        updated_routines = alarm_routines(payload.get("item") or [])

        if payload.get("confirmDataVersion") and payload.get("dataVersion"):
            try:
                confirmed_routines = await self.confirm_data_version(
                    auth_token=auth_token,
                    mac=mac,
                    data_version=payload["dataVersion"],
                    success=True,
                    return_all_routines=True,
                )
                if confirmed_routines:
                    updated_routines = alarm_routines(confirmed_routines)
            except ClientError as error:
                _LOGGER.warning(
                    "Could not confirm scheduled routine data version for %s",
                    mac,
                    exc_info=error,
                )

        return updated_routines

    async def update_scheduled_routine_alarm_weekdays(
        self,
        auth_token: str,
        mac: str,
        alarm: ScheduledRoutineAlarm,
        weekdays: Iterable[str],
    ) -> list[ScheduledRoutineAlarm]:
        payload = await self.edit_scheduled_routines(
            auth_token=auth_token,
            mutable_scheduled_routines=[
                alarm_weekdays_update_payload(alarm, weekdays)
            ],
            routine_type=ALARM_ROUTINE_TYPE,
        )
        updated_routines = alarm_routines(payload.get("item") or [])

        if payload.get("confirmDataVersion") and payload.get("dataVersion"):
            try:
                confirmed_routines = await self.confirm_data_version(
                    auth_token=auth_token,
                    mac=mac,
                    data_version=payload["dataVersion"],
                    success=True,
                    return_all_routines=True,
                )
                if confirmed_routines:
                    updated_routines = alarm_routines(confirmed_routines)
            except ClientError as error:
                _LOGGER.warning(
                    "Could not confirm scheduled routine data version for %s",
                    mac,
                    exc_info=error,
                )

        return updated_routines

    async def edit_scheduled_routines(
        self,
        auth_token: str,
        mutable_scheduled_routines: list[dict[str, Any]],
        routine_type: str,
    ) -> dict:
        url = API_URL + "service/app/routine/v2/editMultiple"
        response: ClientResponse = (
            await self._post_request_with_logging_and_errors_raised(
                url=url,
                auth_token=auth_token,
                json_body={
                    "mrds": mutable_scheduled_routines,
                    "type": routine_type,
                },
            )
        )
        response_json = await response.json()
        return response_json["payload"]

    async def confirm_data_version(
        self,
        auth_token: str,
        mac: str,
        data_version: str,
        success: bool = True,
        return_all_routines: bool = True,
    ) -> list[ScheduledRoutineAlarm]:
        url = API_URL + "service/app/v2/dataVersion"
        response: ClientResponse = (
            await self._post_request_with_logging_and_errors_raised(
                url=url,
                auth_token=auth_token,
                json_body={
                    "dataVersion": data_version,
                    "macAddress": mac,
                    "success": success,
                    "returnAllRoutines": return_all_routines,
                },
            )
        )
        response_json = await response.json()
        return response_json["payload"]

    async def content(
        self, auth_token: str, product: str, content: list, max_retries: int = 3
    ):
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
