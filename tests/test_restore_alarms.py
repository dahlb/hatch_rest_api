"""Original Restore alarms: the Hatch alarm API plus the device's alarm ids.

The flows mirror what the Hatch app was seen doing: on/off syncs the enabled
ids to the device, then saves the list; an edit creates a copy, moves the
device to the copy's id, then deletes the original.
"""

import asyncio
from collections.abc import Callable, Iterable
from concurrent.futures import Future
from copy import deepcopy
from datetime import datetime, time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from aiohttp import ClientError
import pytest

from hatch_rest_api import BaseError, DeviceSyncError, RateError, Restore, restore as restore_module
from hatch_rest_api.hatch import API_URL, RESTORE_ALARM_API_URLS

MAC = "AA:BB:CC:DD:EE:FF"
ZONE = "America/New_York"
SATURDAY = {
    "id": 1001,
    "active": True,
    "enabled": False,
    "daysOfWeek": 64,
    "time": "2026-01-03 08:30:00",
    "absoluteTime": 1767447000000,
    "color": {"duration": 1800, "i": 65535, "id": 29, "until": "duration"},
    "colorStartsEarly": True,
    "isExpiredOneOff": False,
    "macAddress": MAC,
    "sound": {"id": 10024, "v": 65535},
}
WEEKDAYS = {
    **SATURDAY,
    "id": 1002,
    "enabled": True,
    "daysOfWeek": 62,
    "time": "2026-01-05 07:00:00",
    "absoluteTime": 1767614400000,
    "color": {"duration": 1800, "i": 65535, "id": 27, "until": "duration"},
    "sound": {"id": 10024, "v": 64259},
}
PROD_SLEEP = RESTORE_ALARM_API_URLS[1]


def _done(result: Any = None) -> Future:
    """Return a future that has already resolved to ``result``."""
    future: Future = Future()
    future.set_result(result)
    return future


class ConfirmingShadowClient:
    """Shadow stub whose device confirms alarm id lists, unless told not to."""

    def __init__(self, confirm: bool = True) -> None:
        """Confirm alarm id lists when ``confirm`` is set."""
        self.confirm = confirm
        self.published: list[dict[str, Any]] = []
        self.update_callback: Callable[[Any], None] | None = None
        self.version = 1

    def subscribe_to_update_shadow_accepted(
        self, request: Any, qos: Any, callback: Callable[[Any], None]
    ) -> tuple[Future, str]:
        """Keep the update callback, to confirm through."""
        self.update_callback = callback
        return _done(), "update-topic"

    def subscribe_to_get_shadow_accepted(
        self, request: Any, qos: Any, callback: Callable[[Any], None]
    ) -> tuple[Future, str]:
        """Accept the subscription."""
        return _done(), "get-topic"

    def publish_get_shadow(self, request: Any, qos: Any) -> Future:
        """Accept the get request."""
        return _done(MagicMock())

    def publish_update_shadow(self, request: Any, qos: Any) -> Future:
        """Record the desired state; confirm an alarm id list like the device."""
        desired = request.state.desired
        self.published.append(desired)
        ids = desired.get("content", {}).get("requested", {}).get("alarms", {}).get("ids")
        if ids is not None and self.confirm and self.update_callback is not None:
            self.version += 1
            self.update_callback(
                SimpleNamespace(
                    version=self.version,
                    state=SimpleNamespace(
                        reported={
                            "content": {
                                "requested": {
                                    "alarms": {"ids": ids, "status": "success", "reason": "ok"}
                                }
                            }
                        }
                    ),
                )
            )
        return _done()


class FakeAlarmApi:
    """Hatch alarm API stand-in keeping a server-side alarm list."""

    def __init__(self, alarms: list[dict[str, Any]], failing_urls: Iterable[str] = ()) -> None:
        """Hold ``alarms``; fetches from ``failing_urls`` fail like an unsupported host."""
        self.alarms = deepcopy(alarms)
        self.failing_urls = set(failing_urls)
        self.calls: list[tuple[Any, ...]] = []
        self.next_id = 5000

    async def restore_alarms(self, auth_token: str, mac: str, base_url: str) -> list[Any]:
        """Return the active alarms."""
        self.calls.append(("fetch", base_url))
        if base_url in self.failing_urls:
            raise ClientError("Invalid response format from API (status: 404)")
        return [deepcopy(alarm) for alarm in self.alarms if alarm.get("active", True)]

    async def create_restore_alarm(
        self, auth_token: str, alarm: dict[str, Any], base_url: str
    ) -> list[Any]:
        """Add an inactive copy of ``alarm`` under a new id, as Hatch does."""
        self.calls.append(("create", base_url, deepcopy(alarm)))
        created = {**deepcopy(alarm), "id": self.next_id, "active": False, "isExpiredOneOff": False}
        created["sound"] = {"id": alarm["sound"]["id"], "v": alarm["sound"]["v"]}
        self.next_id += 1
        self.alarms.append(created)
        return deepcopy(self.alarms)

    async def update_restore_alarms(
        self, auth_token: str, alarms: list[dict[str, Any]], base_url: str
    ) -> list[Any]:
        """Apply ``alarms`` over the stored ones; return the active ones."""
        self.calls.append(("update", base_url, deepcopy(alarms)))
        sent = {alarm["id"]: alarm for alarm in alarms}
        self.alarms = [{**alarm, **sent.get(alarm["id"], {})} for alarm in self.alarms]
        return [deepcopy(alarm) for alarm in self.alarms if alarm.get("active", True)]

    def calls_of(self, kind: str) -> list[tuple[Any, ...]]:
        """The calls of one kind: fetch, create or update."""
        return [call for call in self.calls if call[0] == kind]


def _restore(
    api: FakeAlarmApi, confirm: bool = True, alarms: list[dict[str, Any]] | None = None
) -> tuple[Restore, ConfirmingShadowClient]:
    """Build a Restore that has loaded alarm 1002 and is wired to ``api``."""
    client = ConfirmingShadowClient(confirm=confirm)
    device = Restore(device_name="Bedroom", thing_name="thing-1", mac=MAC, shadow_client=client)
    device._update_local_state(
        {
            "timezone": ZONE,
            "content": {
                "requested": {"alarms": {"ids": [1002], "status": "success", "reason": "ok"}}
            },
        }
    )
    device.configure_alarm_api(api=api, auth_token="token", alarms=alarms, api_url=None)
    return device, client


def _alarm_writes(client: ConfirmingShadowClient) -> list[list[int]]:
    """The alarm id lists sent to the device, in order."""
    return [
        desired["content"]["requested"]["alarms"]["ids"]
        for desired in client.published
        if "requested" in desired.get("content", {})
    ]


class RestoreAlarmFetchTest(unittest.TestCase):
    """Reading alarms, from whichever host serves them."""

    def test_falls_back_to_the_app_host_and_keeps_using_it(self) -> None:
        """Falls back to the app host and keeps using it."""
        api = FakeAlarmApi([SATURDAY, WEEKDAYS], failing_urls=[API_URL])
        device, _ = _restore(api)

        alarms = asyncio.run(device.refresh_alarms())
        asyncio.run(device.refresh_alarms())

        assert [alarm["id"] for alarm in alarms] == [1001, 1002]
        assert device.alarm_api_url == PROD_SLEEP
        assert device.restore_alarms_loaded
        assert api.calls == [("fetch", API_URL), ("fetch", PROD_SLEEP), ("fetch", PROD_SLEEP)]

    def test_deleted_alarms_are_left_out(self) -> None:
        """Deleted alarms are left out."""
        api = FakeAlarmApi([SATURDAY, {**WEEKDAYS, "active": False}])
        api.restore_alarms = _all_alarms(api)
        device, _ = _restore(api)
        asyncio.run(device.refresh_alarms())
        assert [alarm["id"] for alarm in device.restore_alarms] == [1001]

    def test_raises_when_no_host_answers(self) -> None:
        """Raises when no host answers."""
        api = FakeAlarmApi([SATURDAY], failing_urls=RESTORE_ALARM_API_URLS)
        device, _ = _restore(api)
        with pytest.raises(ClientError):
            asyncio.run(device.refresh_alarms())
        assert not device.restore_alarms_loaded

    def test_rate_limits_are_not_retried_on_the_other_host(self) -> None:
        """Rate limits are not retried on the other host."""
        api = FakeAlarmApi([SATURDAY])

        async def rate_limited(**kwargs: Any) -> list[Any]:
            """Record the call and fail it with a rate limit."""
            api.calls.append(("fetch", kwargs["base_url"]))
            raise RateError("API rate limit exceeded.")

        api.restore_alarms = rate_limited
        device, _ = _restore(api)
        with pytest.raises(RateError):
            asyncio.run(device.refresh_alarms())
        assert len(api.calls) == 1


def _all_alarms(api: FakeAlarmApi) -> Callable[..., Any]:
    """A fetch that also returns deleted alarms."""

    async def fetch(auth_token: str, mac: str, base_url: str) -> list[Any]:
        """Return every stored alarm."""
        api.calls.append(("fetch", base_url))
        return deepcopy(api.alarms)

    return fetch


class RestoreAlarmEnableTest(unittest.TestCase):
    """Turning one alarm on or off."""

    def test_syncs_the_device_before_saving(self) -> None:
        """Syncs the device before saving."""
        api = FakeAlarmApi([SATURDAY, WEEKDAYS])
        device, client = _restore(api)

        alarm_id = asyncio.run(device.set_restore_alarm_enabled(1001, True))

        assert alarm_id == 1001
        assert _alarm_writes(client) == [[1001, 1002]]
        [update] = api.calls_of("update")
        saved = {alarm["id"]: alarm for alarm in update[2]}
        assert saved[1001]["enabled"]
        assert saved[1002]["enabled"]
        # The request shape the app sends.
        assert "isExpiredOneOff" not in saved[1001]
        assert saved[1001]["sound"] == {"id": 10024, "v": 65535, "duration": 0, "until": "duration"}
        assert [call[0] for call in api.calls] == ["fetch", "update"]
        assert device.restore_alarm_by_id(1001)["enabled"]

    def test_turning_the_last_alarm_off_clears_the_device_list(self) -> None:
        """Turning the last alarm off clears the device list."""
        api = FakeAlarmApi([SATURDAY, WEEKDAYS])
        device, client = _restore(api)
        asyncio.run(device.set_restore_alarm_enabled(1002, False))
        assert _alarm_writes(client) == [[]]

    def test_unknown_alarm(self) -> None:
        """Unknown alarm."""
        api = FakeAlarmApi([SATURDAY])
        device, _ = _restore(api)
        with pytest.raises(ValueError):
            asyncio.run(device.set_restore_alarm_enabled(9999, True))
        assert api.calls_of("update") == []


def _create_listing_deleted_alarms(api: FakeAlarmApi) -> Callable[..., Any]:
    """A create whose answer also lists deleted alarms, as Hatch's can."""
    original_create = api.create_restore_alarm

    async def create(auth_token: str, alarm: dict[str, Any], base_url: str) -> list[Any]:
        """Create, then answer with every stored alarm."""
        await original_create(auth_token, alarm, base_url)
        return deepcopy(api.alarms)  # deleted ones included

    return create


class FixedDatetime(datetime):
    """A datetime whose now() is ``fixed_now``."""

    fixed_now: datetime

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        """Return ``fixed_now`` in ``tz``."""
        return cls.fixed_now.astimezone(tz)


class RestoreAlarmEditTest(unittest.TestCase):
    """Changing an alarm's time or days: a copy replaces the original."""

    def test_new_time_is_a_new_alarm_that_replaces_the_original(self) -> None:
        """New time is a new alarm that replaces the original."""
        api = FakeAlarmApi([SATURDAY, WEEKDAYS])
        device, client = _restore(api)

        new_id = asyncio.run(device.set_restore_alarm_schedule(1002, wake_time=time(6, 45)))

        assert new_id == 5000
        [create] = api.calls_of("create")
        sent = create[2]
        assert sent["id"] == 1002
        assert sent["active"]
        assert sent["time"] == "2026-01-05 06:45:00"
        expected = datetime(2026, 1, 5, 6, 45, tzinfo=ZoneInfo(ZONE))
        assert sent["absoluteTime"] == int(expected.timestamp() * 1000)
        assert sent["daysOfWeek"] == 62
        # The device is moved to the copy before the original is deleted.
        assert _alarm_writes(client) == [[5000]]
        [update] = api.calls_of("update")
        assert [(alarm["id"], alarm["active"]) for alarm in update[2]] == [
            (1001, True),
            (1002, False),
            (5000, True),
        ]
        assert [call[0] for call in api.calls] == ["fetch", "create", "update"]
        assert [alarm["id"] for alarm in device.restore_alarms] == [1001, 5000]
        assert restore_module.restore_alarm_wake_time(device.restore_alarm_by_id(5000)) == time(
            6, 45
        )

    def test_a_second_edit_ignores_alarms_deleted_by_the_first(self) -> None:
        """A second edit ignores alarms deleted by the first."""
        # Hatch's create answer can include alarms an earlier edit deleted.
        api = FakeAlarmApi([SATURDAY, WEEKDAYS])
        api.create_restore_alarm = _create_listing_deleted_alarms(api)
        device, client = _restore(api)

        first = asyncio.run(device.set_restore_alarm_schedule(1002, wake_time=time(6, 45)))
        second = asyncio.run(device.set_alarm_weekdays(first, ["saturday"]))

        assert (first, second) == (5000, 5001)
        server = {alarm["id"]: alarm["active"] for alarm in api.alarms}
        assert server == {1001: True, 1002: False, 5000: False, 5001: True}
        assert _alarm_writes(client) == [[5000], [5001]]
        assert [alarm["id"] for alarm in device.restore_alarms] == [1001, 5001]

    def test_new_weekdays_keep_the_time_and_enabled_state(self) -> None:
        """New weekdays keep the time and enabled state."""
        api = FakeAlarmApi([SATURDAY, WEEKDAYS])
        device, client = _restore(api)

        new_id = asyncio.run(device.set_alarm_weekdays(1001, ["saturday", "sunday"]))

        [create] = api.calls_of("create")
        assert create[2]["daysOfWeek"] == 65
        assert create[2]["time"] == "2026-01-03 08:30:00"
        # The original was off, so the copy stays off and is not loaded.
        assert not device.restore_alarm_by_id(new_id)["enabled"]
        assert _alarm_writes(client) == [[1002]]

    def test_no_weekdays_makes_a_one_time_alarm_at_the_next_occurrence(self) -> None:
        """No weekdays makes a one time alarm at the next occurrence."""
        api = FakeAlarmApi([SATURDAY, WEEKDAYS])
        device, _ = _restore(api)
        FixedDatetime.fixed_now = datetime(2026, 3, 10, 8, 0, tzinfo=ZoneInfo(ZONE))

        with patch.object(restore_module, "datetime", FixedDatetime):
            asyncio.run(device.set_restore_alarm_schedule(1002, wake_time=time(7, 0), weekdays=[]))
            asyncio.run(device.set_restore_alarm_schedule(5000, wake_time=time(9, 0)))

        first, second = api.calls_of("create")
        assert first[2]["daysOfWeek"] == 0
        assert first[2]["time"] == "2026-03-11 07:00:00"  # 07:00 has passed today
        assert second[2]["time"] == "2026-03-10 09:00:00"  # 09:00 has not

    def test_unconfirmed_device_saves_nothing_and_restores_its_ids(self) -> None:
        """Unconfirmed device saves nothing and restores its ids."""
        api = FakeAlarmApi([SATURDAY, WEEKDAYS])
        device, client = _restore(api, confirm=False)

        with (
            patch.object(restore_module, "ALARM_SYNC_TIMEOUT", 0.3),
            pytest.raises(DeviceSyncError),
        ):
            asyncio.run(device.set_restore_alarm_schedule(1002, wake_time=time(6, 45)))

        assert _alarm_writes(client) == [[5000], [1002]]
        assert api.calls_of("update") == []
        # The copy Hatch created stays inactive; the original is untouched.
        server = {alarm["id"]: alarm for alarm in api.alarms}
        assert not server[5000]["active"]
        assert server[1002]["active"]

    def test_needs_the_alarm_api(self) -> None:
        """Needs the alarm api."""
        device = Restore(
            device_name="Bedroom",
            thing_name="thing-1",
            mac=MAC,
            shadow_client=ConfirmingShadowClient(),
        )
        with pytest.raises(BaseError):
            asyncio.run(device.refresh_alarms())
        assert not device.alarm_capable


if __name__ == "__main__":
    unittest.main()
