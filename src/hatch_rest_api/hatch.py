"""Client for the Hatch REST API."""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from datetime import time
import logging
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession, __version__
from aiohttp.hdrs import USER_AGENT

from .errors import AuthError, RateError
from .scheduled_routine import (
    ALARM_ROUTINE_TYPE,
    ScheduledRoutineAlarm,
    alarm_routines,
    alarm_update_payload,
    alarm_wake_time_update_payload,
    alarm_weekdays_update_payload,
)
from .util_http import request_with_logging

_LOGGER = logging.getLogger(__name__)

API_URL: str = "https://data.hatchbaby.com/"
# The original Restore's alarms have their own API. The Hatch app calls it on
# prod-sleep.hatchbaby.com; try the host the rest of this library uses first.
RESTORE_ALARM_API_URLS: tuple[str, ...] = (API_URL, "https://prod-sleep.hatchbaby.com/")


def request_with_logging_and_errors(
    func: Callable[..., Awaitable[ClientResponse]],
) -> Callable[..., Awaitable[ClientResponse]]:
    """Wrap a Hatch API request coroutine with status and error handling.

    Args:
        func: Coroutine that performs the request and returns the response.

    Returns:
        The wrapped coroutine. It raises ``RateError`` on HTTP 429, ``AuthError`` when
        the session is invalid, and ``ClientError`` for any other API failure.
    """

    async def request_with_logging_wrapper(*args: Any, **kwargs: Any) -> ClientResponse:
        response = await func(*args, **kwargs)

        if response.status == 429:
            _LOGGER.warning("Rate limited (429) for URL: %s", response.url)
            raise RateError("API rate limit exceeded. Please wait before retrying.")

        try:
            response_json = await response.json()
        except Exception as err:
            try:
                response_text = await response.text()
                _LOGGER.error(
                    "Failed to parse JSON response. Status: %s, Content: %s",
                    response.status,
                    response_text[:500],
                )
            except Exception:  # noqa: BLE001 - best-effort diagnostics only
                _LOGGER.error("Failed to parse response. Status: %s", response.status)
            raise ClientError(
                f"Invalid response format from API (status: {response.status})"
            ) from err

        if response_json.get("status") == "success":
            return response
        # The API returns errorCode as a string (e.g. "1001"), so compare loosely.
        if str(response_json.get("errorCode")) == "1001":
            _LOGGER.debug("error: session invalid")
            raise AuthError
        raise ClientError(f"api error:{response_json.get('message')}")

    return request_with_logging_wrapper


def _scheduled_routine_display_order(routine: ScheduledRoutineAlarm) -> float:
    """Sort key putting routines without a ``displayOrder`` last."""
    display_order = routine.get("displayOrder")
    return float("inf") if display_order is None else display_order


class Hatch:
    """Async client for the Hatch REST API at data.hatchbaby.com."""

    def __init__(self, client_session: ClientSession | None = None) -> None:
        """Create the client, optionally reusing an existing aiohttp session."""
        if client_session is None:
            self.api_session = ClientSession(raise_for_status=True)
        else:
            self.api_session = client_session
        _LOGGER.debug("api_session_version: %s", __version__)

    async def cleanup_client_session(self) -> None:
        """Close the underlying aiohttp session."""
        await self.api_session.close()

    @request_with_logging_and_errors
    @request_with_logging
    async def _post_request_with_logging_and_errors_raised(
        self, url: str, json_body: dict[str, Any] | list[Any], auth_token: str | None = None
    ) -> ClientResponse:
        headers: dict[str, str] = {USER_AGENT: "hatch_rest_api"}
        if auth_token is not None:
            headers["X-HatchBaby-Auth"] = auth_token
        return await self.api_session.post(url=url, json=json_body, headers=headers)

    @request_with_logging
    @request_with_logging_and_errors
    async def _get_request_with_logging_and_errors_raised(
        self, url: str, auth_token: str | None = None, params: dict[str, Any] | None = None
    ) -> ClientResponse:
        headers: dict[str, str] = {USER_AGENT: "hatch_rest_api"}
        if auth_token is not None:
            headers["X-HatchBaby-Auth"] = auth_token
        return await self.api_session.get(url=url, headers=headers, params=params)

    async def login(self, email: str, password: str) -> str:
        """Log in and return a Hatch auth token.

        Args:
            email: Hatch account email.
            password: Hatch account password.

        Returns:
            The auth token for subsequent requests.
        """
        url = API_URL + "public/v1/login"
        json_body = {
            "email": email,
            "password": password,
        }
        response: ClientResponse = await self._post_request_with_logging_and_errors_raised(
            url=url, json_body=json_body
        )
        response_json = await response.json()
        token: str = response_json["token"]
        return token

    async def member(self, auth_token: str) -> dict[str, Any]:
        """Return the account member details."""
        url = API_URL + "service/app/v2/member"
        response: ClientResponse = await self._get_request_with_logging_and_errors_raised(
            url=url, auth_token=auth_token
        )
        response_json = await response.json()
        payload: dict[str, Any] = response_json["payload"]
        return payload

    async def iot_devices(self, auth_token: str) -> list[dict[str, Any]]:
        """Return the account's IoT devices for every supported product."""
        url = API_URL + "service/app/iotDevice/v2/fetch"
        params = {
            "iotProducts": [
                "restMini",
                "restPlus",
                "riot",
                "riotPlus",
                "restBaby",
                # The original Restore; "restoreIot" is the later first gen.
                "restore",
                "restoreIot",
                "restoreV4",
                "restoreV5",
            ]
        }
        response: ClientResponse = await self._get_request_with_logging_and_errors_raised(
            url=url, auth_token=auth_token, params=params
        )
        response_json = await response.json()
        payload: list[dict[str, Any]] = response_json["payload"]
        return payload

    async def token(self, auth_token: str) -> dict[str, Any]:
        """Return the AWS IoT token payload (region, identity id and token)."""
        url = API_URL + "service/app/restPlus/token/v1/fetch"
        response: ClientResponse = await self._get_request_with_logging_and_errors_raised(
            url=url, auth_token=auth_token
        )
        response_json = await response.json()
        payload: dict[str, Any] = response_json["payload"]
        return payload

    async def favorites(self, auth_token: str, mac: str) -> list[dict[str, Any]]:
        """Return the favorites for a device, sorted by display order."""
        url = API_URL + "service/app/routine/v2/fetch"
        params = {"macAddress": mac}
        response: ClientResponse = await self._get_request_with_logging_and_errors_raised(
            url=url, auth_token=auth_token, params=params
        )
        response_json = await response.json()
        favorites: list[dict[str, Any]] = response_json["payload"]
        favorites.sort(key=lambda x: x.get("displayOrder", float("inf")))
        return favorites

    async def routines(self, auth_token: str, mac: str) -> list[dict[str, Any]]:
        """Return the routines for a device, sorted by display order."""
        url = API_URL + "service/app/routine/v2/fetch"
        params = {"macAddress": mac, "types": "routine"}
        response: ClientResponse = await self._get_request_with_logging_and_errors_raised(
            url=url, auth_token=auth_token, params=params
        )
        response_json = await response.json()
        routines: list[dict[str, Any]] = response_json["payload"]
        routines.sort(key=lambda x: x.get("displayOrder", float("inf")))
        return routines

    async def scheduled_routines(
        self,
        auth_token: str,
        mac: str,
        types: list[str] | None = None,
    ) -> list[ScheduledRoutineAlarm]:
        """Return the v3 scheduled routines for a device, sorted by display order.

        Args:
            auth_token: Hatch auth token.
            mac: Device MAC address.
            types: Routine types to include, e.g. ``["alarm"]``; all types if omitted.

        Returns:
            The scheduled routines.
        """
        url = API_URL + "service/app/routine/v3/fetch"
        params: dict[str, str | list[str]] = {"macAddress": mac}
        if types is not None:
            params["types"] = types
        response: ClientResponse = await self._get_request_with_logging_and_errors_raised(
            url=url, auth_token=auth_token, params=params
        )
        response_json = await response.json()
        routines: list[ScheduledRoutineAlarm] = response_json["payload"]
        routines.sort(key=_scheduled_routine_display_order)
        return routines

    async def update_scheduled_routine_alarm_enabled(
        self,
        auth_token: str,
        mac: str,
        alarm: ScheduledRoutineAlarm,
        enabled: bool,
    ) -> list[ScheduledRoutineAlarm]:
        """Enable or disable an alarm.

        Returns:
            The device's alarms after the update.
        """
        return await self._edit_and_confirm_alarm_routines(
            auth_token=auth_token,
            mac=mac,
            mutable_scheduled_routines=[alarm_update_payload(alarm, enabled)],
        )

    async def update_scheduled_routine_alarm_wake_time(
        self,
        auth_token: str,
        mac: str,
        alarm: ScheduledRoutineAlarm,
        wake_time: time,
    ) -> list[ScheduledRoutineAlarm]:
        """Change an alarm's wake time.

        Returns:
            The device's alarms after the update.
        """
        return await self._edit_and_confirm_alarm_routines(
            auth_token=auth_token,
            mac=mac,
            mutable_scheduled_routines=[alarm_wake_time_update_payload(alarm, wake_time)],
        )

    async def update_scheduled_routine_alarm_weekdays(
        self,
        auth_token: str,
        mac: str,
        alarm: ScheduledRoutineAlarm,
        weekdays: Iterable[str],
    ) -> list[ScheduledRoutineAlarm]:
        """Change the days an alarm repeats on.

        Returns:
            The device's alarms after the update.
        """
        return await self._edit_and_confirm_alarm_routines(
            auth_token=auth_token,
            mac=mac,
            mutable_scheduled_routines=[alarm_weekdays_update_payload(alarm, weekdays)],
        )

    async def _edit_and_confirm_alarm_routines(
        self,
        auth_token: str,
        mac: str,
        mutable_scheduled_routines: list[dict[str, Any]],
    ) -> list[ScheduledRoutineAlarm]:
        payload = await self.edit_scheduled_routines(
            auth_token=auth_token,
            mutable_scheduled_routines=mutable_scheduled_routines,
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
                    "Could not confirm scheduled routine data version for %s; "
                    "refetching authoritative routines",
                    mac,
                    exc_info=error,
                )
                updated_routines = alarm_routines(
                    await self.scheduled_routines(
                        auth_token=auth_token,
                        mac=mac,
                        types=[ALARM_ROUTINE_TYPE],
                    )
                )

        return updated_routines

    async def edit_scheduled_routines(
        self,
        auth_token: str,
        mutable_scheduled_routines: list[dict[str, Any]],
        routine_type: str,
    ) -> dict[str, Any]:
        """Submit edits to one or more scheduled routines.

        Args:
            auth_token: Hatch auth token.
            mutable_scheduled_routines: Routine update payloads.
            routine_type: Type of the routines being edited.

        Returns:
            The API payload, including any data version that must be confirmed.
        """
        url = API_URL + "service/app/routine/v2/editMultiple"
        response: ClientResponse = await self._post_request_with_logging_and_errors_raised(
            url=url,
            auth_token=auth_token,
            json_body={
                "mrds": mutable_scheduled_routines,
                "type": routine_type,
            },
        )
        response_json = await response.json()
        payload: dict[str, Any] = response_json["payload"]
        return payload

    async def confirm_data_version(
        self,
        auth_token: str,
        mac: str,
        data_version: str,
        success: bool = True,
        return_all_routines: bool = True,
    ) -> list[ScheduledRoutineAlarm]:
        """Confirm a routine data version after an edit.

        Args:
            auth_token: Hatch auth token.
            mac: Device MAC address.
            data_version: Data version returned by the edit.
            success: Whether the edit should be confirmed as successful.
            return_all_routines: Whether to return all routines in the response.

        Returns:
            The device's routines.
        """
        url = API_URL + "service/app/v2/dataVersion"
        response: ClientResponse = await self._post_request_with_logging_and_errors_raised(
            url=url,
            auth_token=auth_token,
            json_body={
                "dataVersion": data_version,
                "macAddress": mac,
                "success": success,
                "returnAllRoutines": return_all_routines,
            },
        )
        response_json = await response.json()
        payload: list[ScheduledRoutineAlarm] = response_json["payload"]
        return payload

    async def restore_alarms(
        self, auth_token: str, mac: str, base_url: str = API_URL
    ) -> list[dict[str, Any]]:
        """Fetch every alarm of an original Restore, deleted ones included.

        Args:
            auth_token: Hatch auth token.
            mac: The device's MAC address.
            base_url: Which alarm API host to call, see ``RESTORE_ALARM_API_URLS``.

        Returns:
            The alarms; a deleted one has ``"active": false``.
        """
        response: ClientResponse = await self._get_request_with_logging_and_errors_raised(
            url=f"{base_url}service/app/alarm/v1/fetch/{mac}", auth_token=auth_token
        )
        response_json = await response.json()
        payload: list[dict[str, Any]] = response_json["payload"]
        return payload

    async def create_restore_alarm(
        self, auth_token: str, alarm: dict[str, Any], base_url: str = API_URL
    ) -> list[dict[str, Any]]:
        """Create an original Restore alarm.

        Args:
            auth_token: Hatch auth token.
            alarm: The alarm to create, as the Hatch app sends it.
            base_url: Which alarm API host to call, see ``RESTORE_ALARM_API_URLS``.

        Returns:
            The device's alarms, the new one still ``"active": false``.
        """
        response: ClientResponse = await self._post_request_with_logging_and_errors_raised(
            url=f"{base_url}service/app/alarm/v1/create",
            auth_token=auth_token,
            json_body=alarm,
        )
        response_json = await response.json()
        payload: list[dict[str, Any]] = response_json["payload"]
        return payload

    async def update_restore_alarms(
        self, auth_token: str, alarms: list[dict[str, Any]], base_url: str = API_URL
    ) -> list[dict[str, Any]]:
        """Replace an original Restore's alarm list.

        Args:
            auth_token: Hatch auth token.
            alarms: Every alarm; one sent with ``"active": false`` is deleted.
            base_url: Which alarm API host to call, see ``RESTORE_ALARM_API_URLS``.

        Returns:
            The device's remaining alarms.
        """
        response: ClientResponse = await self._post_request_with_logging_and_errors_raised(
            url=f"{base_url}service/app/alarm/v1/update",
            auth_token=auth_token,
            json_body=alarms,
        )
        response_json = await response.json()
        payload: list[dict[str, Any]] = response_json["payload"]
        return payload

    async def content(
        self, auth_token: str, product: str, content: list[str], max_retries: int = 3
    ) -> dict[str, Any]:
        """Fetch content for a product, retrying with backoff when rate limited.

        Args:
            auth_token: Hatch auth token.
            product: Product name, e.g. ``"riot"``.
            content: Content types to fetch: ``"sound"``, ``"color"`` and/or ``"windDown"``.
            max_retries: Number of retries after a rate-limit response.

        Returns:
            The content payload, with the items under ``contentItems``.
        """
        url = API_URL + "service/app/content/v1/fetchByProduct"
        params = {"product": product, "contentTypes": content}

        retry_count = 0
        while True:
            try:
                response: ClientResponse = await self._get_request_with_logging_and_errors_raised(
                    url=url, auth_token=auth_token, params=params
                )
                response_json: dict[str, dict[str, Any]] = await response.json()
                return response_json["payload"]
            except RateError:
                retry_count += 1
                if retry_count > max_retries:
                    _LOGGER.error("Maximum retries (%s) exceeded for content API call", max_retries)
                    raise

                # Calculate exponential backoff wait time (2^retry_count seconds)
                wait_time = 2**retry_count
                _LOGGER.warning(
                    "Rate limited. Retrying in %s seconds (attempt %s/%s)",
                    wait_time,
                    retry_count,
                    max_retries,
                )
                await asyncio.sleep(wait_time)
