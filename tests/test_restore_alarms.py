"""Original Restore alarms: the Hatch alarm API plus the device's alarm ids.

The flows mirror what the Hatch app was seen doing: on/off syncs the enabled
ids to the device, then saves the list; an edit creates a copy, moves the
device to the copy's id, then deletes the original.
"""

import asyncio
import unittest
from concurrent.futures import Future
from copy import deepcopy
from datetime import datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from aiohttp import ClientError

from hatch_rest_api import DeviceSyncError, RateError, Restore
from hatch_rest_api import restore as restore_module
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


def _done(result=None) -> Future:
    future: Future = Future()
    future.set_result(result)
    return future


class ConfirmingShadowClient:
    """Shadow stub whose device confirms alarm id lists, unless told not to."""

    def __init__(self, confirm: bool = True):
        self.confirm = confirm
        self.published = []
        self.update_callback = None
        self.version = 1

    def subscribe_to_update_shadow_accepted(self, request, qos, callback):
        self.update_callback = callback
        return _done(), "update-topic"

    def subscribe_to_get_shadow_accepted(self, request, qos, callback):
        return _done(), "get-topic"

    def publish_get_shadow(self, request, qos):
        return _done(MagicMock())

    def publish_update_shadow(self, request, qos):
        desired = request.state.desired
        self.published.append(desired)
        ids = desired.get("content", {}).get("requested", {}).get("alarms", {}).get("ids")
        if ids is not None and self.confirm:
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

    def __init__(self, alarms, failing_urls=()):
        self.alarms = deepcopy(alarms)
        self.failing_urls = set(failing_urls)
        self.calls = []
        self.next_id = 5000

    async def restore_alarms(self, auth_token, mac, base_url):
        self.calls.append(("fetch", base_url))
        if base_url in self.failing_urls:
            raise ClientError("Invalid response format from API (status: 404)")
        return [deepcopy(alarm) for alarm in self.alarms if alarm.get("active", True)]

    async def create_restore_alarm(self, auth_token, alarm, base_url):
        self.calls.append(("create", base_url, deepcopy(alarm)))
        created = {**deepcopy(alarm), "id": self.next_id, "active": False, "isExpiredOneOff": False}
        created["sound"] = {"id": alarm["sound"]["id"], "v": alarm["sound"]["v"]}
        self.next_id += 1
        self.alarms.append(created)
        return deepcopy(self.alarms)

    async def update_restore_alarms(self, auth_token, alarms, base_url):
        self.calls.append(("update", base_url, deepcopy(alarms)))
        sent = {alarm["id"]: alarm for alarm in alarms}
        self.alarms = [{**alarm, **sent.get(alarm["id"], {})} for alarm in self.alarms]
        return [deepcopy(alarm) for alarm in self.alarms if alarm.get("active", True)]

    def calls_of(self, kind):
        return [call for call in self.calls if call[0] == kind]


def _restore(api, confirm=True, alarms=None):
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


def _alarm_writes(client):
    return [
        desired["content"]["requested"]["alarms"]["ids"]
        for desired in client.published
        if "requested" in desired.get("content", {})
    ]


class RestoreAlarmFetchTest(unittest.TestCase):
    def test_falls_back_to_the_app_host_and_keeps_using_it(self):
        api = FakeAlarmApi([SATURDAY, WEEKDAYS], failing_urls=[API_URL])
        device, _ = _restore(api)

        alarms = asyncio.run(device.refresh_alarms())
        asyncio.run(device.refresh_alarms())

        self.assertEqual([alarm["id"] for alarm in alarms], [1001, 1002])
        self.assertEqual(device.alarm_api_url, PROD_SLEEP)
        self.assertTrue(device.restore_alarms_loaded)
        self.assertEqual(api.calls, [("fetch", API_URL), ("fetch", PROD_SLEEP), ("fetch", PROD_SLEEP)])

    def test_deleted_alarms_are_left_out(self):
        api = FakeAlarmApi([SATURDAY, {**WEEKDAYS, "active": False}])
        api.restore_alarms = _all_alarms(api)
        device, _ = _restore(api)
        asyncio.run(device.refresh_alarms())
        self.assertEqual([alarm["id"] for alarm in device.restore_alarms], [1001])

    def test_raises_when_no_host_answers(self):
        api = FakeAlarmApi([SATURDAY], failing_urls=RESTORE_ALARM_API_URLS)
        device, _ = _restore(api)
        with self.assertRaises(ClientError):
            asyncio.run(device.refresh_alarms())
        self.assertFalse(device.restore_alarms_loaded)

    def test_rate_limits_are_not_retried_on_the_other_host(self):
        api = FakeAlarmApi([SATURDAY])

        async def rate_limited(**kwargs):
            api.calls.append(("fetch", kwargs["base_url"]))
            raise RateError("API rate limit exceeded.")

        api.restore_alarms = rate_limited
        device, _ = _restore(api)
        with self.assertRaises(RateError):
            asyncio.run(device.refresh_alarms())
        self.assertEqual(len(api.calls), 1)


def _all_alarms(api):
    async def fetch(auth_token, mac, base_url):
        api.calls.append(("fetch", base_url))
        return deepcopy(api.alarms)

    return fetch


class RestoreAlarmEnableTest(unittest.TestCase):
    def test_syncs_the_device_before_saving(self):
        api = FakeAlarmApi([SATURDAY, WEEKDAYS])
        device, client = _restore(api)

        alarm_id = asyncio.run(device.set_restore_alarm_enabled(1001, True))

        self.assertEqual(alarm_id, 1001)
        self.assertEqual(_alarm_writes(client), [[1001, 1002]])
        [update] = api.calls_of("update")
        saved = {alarm["id"]: alarm for alarm in update[2]}
        self.assertTrue(saved[1001]["enabled"])
        self.assertTrue(saved[1002]["enabled"])
        # The request shape the app sends.
        self.assertNotIn("isExpiredOneOff", saved[1001])
        self.assertEqual(saved[1001]["sound"], {"id": 10024, "v": 65535, "duration": 0, "until": "duration"})
        self.assertEqual([call[0] for call in api.calls], ["fetch", "update"])
        self.assertTrue(device.restore_alarm_by_id(1001)["enabled"])

    def test_turning_the_last_alarm_off_clears_the_device_list(self):
        api = FakeAlarmApi([SATURDAY, WEEKDAYS])
        device, client = _restore(api)
        asyncio.run(device.set_restore_alarm_enabled(1002, False))
        self.assertEqual(_alarm_writes(client), [[]])

    def test_unknown_alarm(self):
        api = FakeAlarmApi([SATURDAY])
        device, _ = _restore(api)
        with self.assertRaises(ValueError):
            asyncio.run(device.set_restore_alarm_enabled(9999, True))
        self.assertEqual(api.calls_of("update"), [])


def _create_listing_deleted_alarms(api):
    original_create = api.create_restore_alarm

    async def create(auth_token, alarm, base_url):
        await original_create(auth_token, alarm, base_url)
        return deepcopy(api.alarms)  # deleted ones included

    return create


class FixedDatetime(datetime):
    fixed_now: datetime

    @classmethod
    def now(cls, tz=None):
        return cls.fixed_now.astimezone(tz)


class RestoreAlarmEditTest(unittest.TestCase):
    def test_new_time_is_a_new_alarm_that_replaces_the_original(self):
        api = FakeAlarmApi([SATURDAY, WEEKDAYS])
        device, client = _restore(api)

        new_id = asyncio.run(device.set_restore_alarm_schedule(1002, wake_time=time(6, 45)))

        self.assertEqual(new_id, 5000)
        [create] = api.calls_of("create")
        sent = create[2]
        self.assertEqual(sent["id"], 1002)
        self.assertTrue(sent["active"])
        self.assertEqual(sent["time"], "2026-01-05 06:45:00")
        expected = datetime(2026, 1, 5, 6, 45, tzinfo=ZoneInfo(ZONE))
        self.assertEqual(sent["absoluteTime"], int(expected.timestamp() * 1000))
        self.assertEqual(sent["daysOfWeek"], 62)
        # The device is moved to the copy before the original is deleted.
        self.assertEqual(_alarm_writes(client), [[5000]])
        [update] = api.calls_of("update")
        self.assertEqual(
            [(alarm["id"], alarm["active"]) for alarm in update[2]],
            [(1001, True), (1002, False), (5000, True)],
        )
        self.assertEqual([call[0] for call in api.calls], ["fetch", "create", "update"])
        self.assertEqual([alarm["id"] for alarm in device.restore_alarms], [1001, 5000])
        self.assertEqual(
            restore_module.restore_alarm_wake_time(device.restore_alarm_by_id(5000)), time(6, 45)
        )

    def test_a_second_edit_ignores_alarms_deleted_by_the_first(self):
        # Hatch's create answer can include alarms an earlier edit deleted.
        api = FakeAlarmApi([SATURDAY, WEEKDAYS])
        api.create_restore_alarm = _create_listing_deleted_alarms(api)
        device, client = _restore(api)

        first = asyncio.run(device.set_restore_alarm_schedule(1002, wake_time=time(6, 45)))
        second = asyncio.run(device.set_alarm_weekdays(first, ["saturday"]))

        self.assertEqual((first, second), (5000, 5001))
        server = {alarm["id"]: alarm["active"] for alarm in api.alarms}
        self.assertEqual(server, {1001: True, 1002: False, 5000: False, 5001: True})
        self.assertEqual(_alarm_writes(client), [[5000], [5001]])
        self.assertEqual([alarm["id"] for alarm in device.restore_alarms], [1001, 5001])

    def test_new_weekdays_keep_the_time_and_enabled_state(self):
        api = FakeAlarmApi([SATURDAY, WEEKDAYS])
        device, client = _restore(api)

        new_id = asyncio.run(device.set_alarm_weekdays(1001, ["saturday", "sunday"]))

        [create] = api.calls_of("create")
        self.assertEqual(create[2]["daysOfWeek"], 65)
        self.assertEqual(create[2]["time"], "2026-01-03 08:30:00")
        # The original was off, so the copy stays off and is not loaded.
        self.assertFalse(device.restore_alarm_by_id(new_id)["enabled"])
        self.assertEqual(_alarm_writes(client), [[1002]])

    def test_no_weekdays_makes_a_one_time_alarm_at_the_next_occurrence(self):
        api = FakeAlarmApi([SATURDAY, WEEKDAYS])
        device, _ = _restore(api)
        FixedDatetime.fixed_now = datetime(2026, 3, 10, 8, 0, tzinfo=ZoneInfo(ZONE))

        with patch.object(restore_module, "datetime", FixedDatetime):
            asyncio.run(device.set_restore_alarm_schedule(1002, wake_time=time(7, 0), weekdays=[]))
            asyncio.run(device.set_restore_alarm_schedule(5000, wake_time=time(9, 0)))

        first, second = api.calls_of("create")
        self.assertEqual(first[2]["daysOfWeek"], 0)
        self.assertEqual(first[2]["time"], "2026-03-11 07:00:00")  # 07:00 has passed today
        self.assertEqual(second[2]["time"], "2026-03-10 09:00:00")  # 09:00 has not

    def test_unconfirmed_device_saves_nothing_and_restores_its_ids(self):
        api = FakeAlarmApi([SATURDAY, WEEKDAYS])
        device, client = _restore(api, confirm=False)

        with patch.object(restore_module, "ALARM_SYNC_TIMEOUT", 0.3), self.assertRaises(DeviceSyncError):
            asyncio.run(device.set_restore_alarm_schedule(1002, wake_time=time(6, 45)))

        self.assertEqual(_alarm_writes(client), [[5000], [1002]])
        self.assertEqual(api.calls_of("update"), [])
        # The copy Hatch created stays inactive; the original is untouched.
        server = {alarm["id"]: alarm for alarm in api.alarms}
        self.assertFalse(server[5000]["active"])
        self.assertTrue(server[1002]["active"])

    def test_needs_the_alarm_api(self):
        device = Restore(
            device_name="Bedroom", thing_name="thing-1", mac=MAC, shadow_client=ConfirmingShadowClient()
        )
        with self.assertRaises(RuntimeError):
            asyncio.run(device.refresh_alarms())
        self.assertFalse(device.alarm_capable)


if __name__ == "__main__":
    unittest.main()
