"""Original Restore construction, shadow parsing and routine writes."""

import asyncio
from collections.abc import Callable
from concurrent.futures import Future
import json
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import AsyncMock, MagicMock

import pytest

from hatch_rest_api import Hatch, RestDevice, Restore
from hatch_rest_api.hatch import API_URL, RESTORE_ALARM_API_URLS
from hatch_rest_api.restore import RESTORE_STATE_FIELDS
from hatch_rest_api.util import clean_for_logging

# A report shaped like the original Restore's shadow, as documented by
# homebridge-hatch-baby-rest's RestoreState. Hardware details trimmed.
FULL_STATE = {
    "alarmsDisabled": False,
    "snoozeDuration": 540,
    "env": "prod",
    "color": {"id": 3, "i": 32767, "enabled": True},
    "sound": {"id": 10005, "v": 19660, "enabled": True},
    "deviceDefaults": {"colorId": 3, "i": 32767, "soundId": 10005, "v": 19660},
    "restoreClock": {
        "i": 6553,
        "turnOffAt": "22:00:00",
        "turnOnAt": "06:00:00",
        "flags": 0,
        "turnOffMode": "never",
    },
    "content": {
        "playing": "routine",
        "startTime": 1700000000,
        "paused": False,
        "pausedAt": 0,
        "offset": 0,
        "step": 2,
        "routineId": 123456,
        "adhocId": 0,
        "alarmId": 0,
        "alarmIds": [11, 12],
    },
    "timezone": "America/New_York",
    "deviceInfo": {"f": "3.2.1", "fR": 1, "hwVersion": "R1"},
    "connected": True,
    "rssi": -44,
}


def _done(result: Any = None) -> Future:
    """Return a future that has already resolved to ``result``."""
    future: Future = Future()
    future.set_result(result)
    return future


class StubShadowClient:
    """IotShadowClient stub that hands the subscribed callbacks back to tests."""

    def __init__(self) -> None:
        """Start with nothing published and no callbacks."""
        self.published: list[dict[str, Any]] = []
        self.get_callback: Callable[[Any], None] | None = None
        self.update_callback: Callable[[Any], None] | None = None

    def subscribe_to_update_shadow_accepted(
        self, request: Any, qos: Any, callback: Callable[[Any], None]
    ) -> tuple[Future, str]:
        """Keep the update callback."""
        self.update_callback = callback
        return _done(), f"$aws/things/{request.thing_name}/shadow/update/accepted"

    def subscribe_to_get_shadow_accepted(
        self, request: Any, qos: Any, callback: Callable[[Any], None]
    ) -> tuple[Future, str]:
        """Keep the get callback."""
        self.get_callback = callback
        return _done(), f"$aws/things/{request.thing_name}/shadow/get/accepted"

    def publish_get_shadow(self, request: Any, qos: Any) -> Future:
        """Accept the get request."""
        return _done(MagicMock())

    def publish_update_shadow(self, request: Any, qos: Any) -> Future:
        """Record the desired state sent."""
        self.published.append(request.state.desired)
        return _done()

    def report(self, reported: dict[str, Any], version: int = 1) -> None:
        """Deliver ``reported`` as a get response."""
        assert self.get_callback is not None
        self.get_callback(_shadow_response(reported, version))

    def report_update(self, reported: dict[str, Any], version: int = 2) -> None:
        """Deliver ``reported`` as an update notification."""
        assert self.update_callback is not None
        self.update_callback(_shadow_response(reported, version))


def _shadow_response(reported: dict[str, Any], version: int = 1) -> SimpleNamespace:
    """Build a shadow response carrying ``reported``."""
    return SimpleNamespace(version=version, state=SimpleNamespace(reported=reported, delta=None))


def _restore(**kwargs: Any) -> tuple[Restore, StubShadowClient]:
    """Build a Restore on a stub shadow client."""
    client = StubShadowClient()
    device = Restore(
        device_name="Bedroom",
        thing_name="thing-1",
        mac="AA:BB:CC:DD:EE:FF",
        shadow_client=client,
        **kwargs,
    )
    return device, client


class RestoreConstructionTest(unittest.TestCase):
    """A new Restore, before and as its first report arrives."""

    def test_is_a_rest_device(self) -> None:
        """Is a rest device."""
        device, _ = _restore()
        assert isinstance(device, RestDevice)

    def test_defaults_before_any_report(self) -> None:
        """Defaults before any report."""
        device, _ = _restore()
        assert not device.is_online
        assert not device.is_on
        assert device.shadow_state == {}
        assert device.routines is None
        # No favorites, so ha_hatch creates no scenes for it.
        assert device.favorites == []

    def test_keeps_probed_routines(self) -> None:
        """Keeps probed routines."""
        routines = [{"id": 1, "name": "Bedtime"}]
        device, _ = _restore(routines=routines)
        assert device.routines == routines

    def test_instances_do_not_share_state(self) -> None:
        """Instances do not share state."""
        _first, first_client = _restore()
        second, _ = _restore()
        first_client.report(FULL_STATE)
        assert second.shadow_state == {}
        assert second.alarm_ids == []


class RestoreStateTest(unittest.TestCase):
    """Reported shadow state, mapped onto attributes."""

    def setUp(self) -> None:
        """Deliver a full report."""
        self.device, self.client = _restore()
        self.client.report(FULL_STATE)

    def test_parses_the_restore_layout(self) -> None:
        """Parses the restore layout."""
        device = self.device
        assert device.firmware_version == "3.2.1"
        assert device.hardware_version == "R1"
        assert device.is_online
        assert device.rssi == -44
        assert device.timezone == "America/New_York"
        assert device.current_playing == "routine"
        assert device.current_step == 2
        assert device.routine_id == 123456
        assert not device.paused
        assert device.alarm_ids == [11, 12]
        assert device.sound_id == 10005
        assert device.volume == 30
        assert device.sound_enabled
        assert device.color_id == 3
        assert device.brightness == 50
        assert device.clock_brightness == 10
        assert device.clock_turn_on_at == "06:00:00"
        assert device.clock_turn_off_at == "22:00:00"
        assert device.clock_turn_off_mode == "never"
        assert not device.alarms_disabled
        assert device.snooze_duration == 540

    def test_playing_anything_counts_as_on(self) -> None:
        """Playing anything counts as on."""
        for playing, expected in (("routine", True), ("remote", True), ("none", False)):
            self.client.report_update({"content": {"playing": playing}})
            assert self.device.is_on is expected, playing
            assert self.device.is_playing is expected, playing

    def test_partial_update_keeps_everything_else(self) -> None:
        """Partial update keeps everything else."""
        self.client.report_update({"content": {"playing": "none", "step": 0}})
        assert self.device.current_playing == "none"
        assert self.device.firmware_version == "3.2.1"
        assert self.device.volume == 30
        # The accumulated raw state keeps the keys the update did not carry.
        content = self.device.shadow_state["content"]
        assert content["playing"] == "none"
        assert content["routineId"] == 123456
        assert self.device.shadow_state["deviceInfo"]["f"] == "3.2.1"

    def test_does_not_read_the_restore_iot_layout(self) -> None:
        """Does not read the restore iot layout."""
        device, client = _restore()
        client.report({"current": {"playing": "remote", "sound": {"v": 65535}}})
        assert device.current_playing == "none"
        assert device.volume == 0

    def test_an_unexpected_value_does_not_lose_the_rest(self) -> None:
        """An unexpected value does not lose the rest."""
        device, client = _restore()
        client.report(
            {
                "rssi": "weak",
                "content": {"alarmIds": "11,12", "playing": "remote"},
                "deviceInfo": {"f": "3.2.1"},
            }
        )
        assert device.rssi is None
        assert device.alarm_ids == []
        assert device.current_playing == "remote"
        assert device.firmware_version == "3.2.1"

    def test_notifies_listeners(self) -> None:
        """Notifies listeners."""
        listener = MagicMock()
        self.device.register_callback(listener)
        self.client.report_update({"content": {"playing": "none"}})
        listener.assert_called_once_with()

    def test_repr_is_a_dict_with_the_raw_state(self) -> None:
        """Repr is a dict with the raw state."""
        representation = self.device.__repr__()
        assert isinstance(representation, dict)
        assert representation["shadow_state"] == FULL_STATE
        for attribute, _, _ in RESTORE_STATE_FIELDS:
            assert attribute in representation
        assert representation["is_on"] is True


class RestoreProbeLoggingTest(unittest.TestCase):
    """Raw reports are logged, since this model's keys are not documented."""

    def test_logs_every_raw_report_as_json(self) -> None:
        """Logs every raw report as json."""
        _device, client = _restore()
        with self.assertLogs("hatch_rest_api.restore", level="DEBUG") as logs:
            client.report(FULL_STATE)
        prefix = "restore raw shadow state for Bedroom: "
        raw = [
            record.getMessage() for record in logs.records if record.getMessage().startswith(prefix)
        ]
        assert len(raw) == 1
        assert json.loads(raw[0][len(prefix) :]) == FULL_STATE


class RestoreWriteTest(unittest.TestCase):
    """The only writes known to work on this model, from homebridge-hatch-baby-rest."""

    def setUp(self) -> None:
        """Build an idle device."""
        self.device, self.client = _restore()

    def test_turn_on_routine(self) -> None:
        """Turn on routine."""
        self.device.turn_on_routine()
        assert self.client.published == [
            {"content": {"playing": "routine", "paused": False, "offset": 0, "step": 1}}
        ]

    def test_turn_on_routine_at_a_later_step(self) -> None:
        """Turn on routine at a later step."""
        self.device.turn_on_routine(step=3)
        assert self.client.published[0]["content"]["step"] == 3

    def test_routine_steps_start_at_one(self) -> None:
        """Routine steps start at one."""
        with pytest.raises(ValueError):
            self.device.turn_on_routine(step=0)
        assert self.client.published == []

    def test_turn_off(self) -> None:
        """Turn off."""
        self.device.turn_off()
        assert self.client.published == [
            {"content": {"playing": "none", "paused": False, "offset": 0, "step": 0}}
        ]


class IotProductsTest(unittest.TestCase):
    """The device list asks Hatch for this product."""

    def test_requests_the_original_restore(self) -> None:
        """Requests the original restore."""
        response = MagicMock()
        response.json = AsyncMock(return_value={"payload": []})
        api = Hatch(client_session=MagicMock())
        api._get_request_with_logging_and_errors_raised = AsyncMock(return_value=response)

        asyncio.run(api.iot_devices(auth_token="auth-token"))

        products = api._get_request_with_logging_and_errors_raised.call_args.kwargs["params"][
            "iotProducts"
        ]
        assert "restore" in products
        assert "restoreIot" in products


def _hatch_answering(payload: Any) -> tuple[Hatch, AsyncMock, AsyncMock]:
    """A Hatch client whose GET and POST helpers answer with ``payload``."""
    response = MagicMock()
    response.json = AsyncMock(return_value={"payload": payload})
    api = Hatch(client_session=MagicMock())
    get = AsyncMock(return_value=response)
    post = AsyncMock(return_value=response)
    api._get_request_with_logging_and_errors_raised = get
    api._post_request_with_logging_and_errors_raised = post
    return api, get, post


class RestoreAlarmApiCallsTest(unittest.TestCase):
    """The three alarm API calls hit the host they are given."""

    def test_fetch(self) -> None:
        """Fetches by MAC address from the given host."""
        api, get, _ = _hatch_answering([{"id": 1}])

        alarms = asyncio.run(
            api.restore_alarms(auth_token="token", mac="AA:BB", base_url=RESTORE_ALARM_API_URLS[1])
        )

        assert alarms == [{"id": 1}]
        assert get.call_args.kwargs == {
            "url": "https://prod-sleep.hatchbaby.com/service/app/alarm/v1/fetch/AA:BB",
            "auth_token": "token",
        }

    def test_create(self) -> None:
        """Creates with the alarm as the body, defaulting to the library's host."""
        api, _, post = _hatch_answering([{"id": 2}])

        alarms = asyncio.run(api.create_restore_alarm(auth_token="token", alarm={"id": 1}))

        assert alarms == [{"id": 2}]
        assert post.call_args.kwargs == {
            "url": f"{API_URL}service/app/alarm/v1/create",
            "auth_token": "token",
            "json_body": {"id": 1},
        }

    def test_update(self) -> None:
        """Updates with the whole list as the body."""
        api, _, post = _hatch_answering([{"id": 1}])

        alarms = asyncio.run(
            api.update_restore_alarms(auth_token="token", alarms=[{"id": 1}, {"id": 2}])
        )

        assert alarms == [{"id": 1}]
        assert post.call_args.kwargs["url"] == f"{API_URL}service/app/alarm/v1/update"
        assert post.call_args.kwargs["json_body"] == [{"id": 1}, {"id": 2}]


class CleanForLoggingTest(unittest.TestCase):
    """List request bodies, like the alarm update's, are redacted too."""

    def test_masks_each_dict_in_a_list(self) -> None:
        """Masks sensitive keys in every dict of a list."""
        cleaned = clean_for_logging([{"password": "hunter2", "id": 1}, "plain"])

        assert cleaned == [{"password": "***", "id": 1}, "plain"]

    def test_masks_a_dict_and_leaves_anything_else(self) -> None:
        """Masks a dict like clean_dictionary_for_logging; returns other values as is."""
        assert clean_for_logging({"username": "someone"}) == {"username": "***"}
        assert clean_for_logging("text") == "text"


if __name__ == "__main__":
    unittest.main()
