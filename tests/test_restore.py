import asyncio
import json
import unittest
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from hatch_rest_api import Hatch, RestDevice, Restore
from hatch_rest_api.restore import RESTORE_STATE_FIELDS

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


def _done(result=None) -> Future:
    future: Future = Future()
    future.set_result(result)
    return future


class StubShadowClient:
    """IotShadowClient stub that hands the subscribed callbacks back to tests."""

    def __init__(self):
        self.published = []
        self.get_callback = None
        self.update_callback = None

    def subscribe_to_update_shadow_accepted(self, request, qos, callback):
        self.update_callback = callback
        return _done(), f"$aws/things/{request.thing_name}/shadow/update/accepted"

    def subscribe_to_get_shadow_accepted(self, request, qos, callback):
        self.get_callback = callback
        return _done(), f"$aws/things/{request.thing_name}/shadow/get/accepted"

    def publish_get_shadow(self, request, qos):
        return _done(MagicMock())

    def publish_update_shadow(self, request, qos):
        self.published.append(request.state.desired)
        return _done()


def _shadow_response(reported, version=1):
    return SimpleNamespace(
        version=version, state=SimpleNamespace(reported=reported, delta=None)
    )


def _restore(**kwargs):
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
    def test_is_a_rest_device(self):
        device, _ = _restore()
        self.assertIsInstance(device, RestDevice)

    def test_defaults_before_any_report(self):
        device, _ = _restore()
        self.assertFalse(device.is_online)
        self.assertFalse(device.is_on)
        self.assertEqual(device.shadow_state, {})
        self.assertIsNone(device.routines)
        # No favorites, so ha_hatch creates no scenes for it.
        self.assertEqual(device.favorites, [])

    def test_keeps_probed_routines(self):
        routines = [{"id": 1, "name": "Bedtime"}]
        device, _ = _restore(routines=routines)
        self.assertEqual(device.routines, routines)

    def test_instances_do_not_share_state(self):
        first, first_client = _restore()
        second, _ = _restore()
        first_client.get_callback(_shadow_response(FULL_STATE))
        self.assertEqual(second.shadow_state, {})
        self.assertEqual(second.alarm_ids, [])


class RestoreStateTest(unittest.TestCase):
    def setUp(self):
        self.device, self.client = _restore()
        self.client.get_callback(_shadow_response(FULL_STATE))

    def test_parses_the_restore_layout(self):
        device = self.device
        self.assertEqual(device.firmware_version, "3.2.1")
        self.assertEqual(device.hardware_version, "R1")
        self.assertTrue(device.is_online)
        self.assertEqual(device.rssi, -44)
        self.assertEqual(device.timezone, "America/New_York")
        self.assertEqual(device.current_playing, "routine")
        self.assertEqual(device.current_step, 2)
        self.assertEqual(device.routine_id, 123456)
        self.assertFalse(device.paused)
        self.assertEqual(device.alarm_ids, [11, 12])
        self.assertEqual(device.sound_id, 10005)
        self.assertEqual(device.volume, 30)
        self.assertTrue(device.sound_enabled)
        self.assertEqual(device.color_id, 3)
        self.assertEqual(device.brightness, 50)
        self.assertEqual(device.clock_brightness, 10)
        self.assertEqual(device.clock_turn_on_at, "06:00:00")
        self.assertEqual(device.clock_turn_off_at, "22:00:00")
        self.assertEqual(device.clock_turn_off_mode, "never")
        self.assertFalse(device.alarms_disabled)
        self.assertEqual(device.snooze_duration, 540)

    def test_playing_anything_counts_as_on(self):
        for playing, expected in (("routine", True), ("remote", True), ("none", False)):
            self.client.update_callback(
                _shadow_response({"content": {"playing": playing}}, version=2)
            )
            self.assertIs(self.device.is_on, expected, playing)
            self.assertIs(self.device.is_playing, expected, playing)

    def test_partial_update_keeps_everything_else(self):
        self.client.update_callback(
            _shadow_response({"content": {"playing": "none", "step": 0}}, version=2)
        )
        self.assertEqual(self.device.current_playing, "none")
        self.assertEqual(self.device.firmware_version, "3.2.1")
        self.assertEqual(self.device.volume, 30)
        # The accumulated raw state keeps the keys the update did not carry.
        content = self.device.shadow_state["content"]
        self.assertEqual(content["playing"], "none")
        self.assertEqual(content["routineId"], 123456)
        self.assertEqual(self.device.shadow_state["deviceInfo"]["f"], "3.2.1")

    def test_does_not_read_the_restore_iot_layout(self):
        device, client = _restore()
        client.get_callback(
            _shadow_response({"current": {"playing": "remote", "sound": {"v": 65535}}})
        )
        self.assertEqual(device.current_playing, "none")
        self.assertEqual(device.volume, 0)

    def test_an_unexpected_value_does_not_lose_the_rest(self):
        device, client = _restore()
        client.get_callback(
            _shadow_response(
                {
                    "rssi": "weak",
                    "content": {"alarmIds": "11,12", "playing": "remote"},
                    "deviceInfo": {"f": "3.2.1"},
                }
            )
        )
        self.assertIsNone(device.rssi)
        self.assertEqual(device.alarm_ids, [])
        self.assertEqual(device.current_playing, "remote")
        self.assertEqual(device.firmware_version, "3.2.1")

    def test_notifies_listeners(self):
        listener = MagicMock()
        self.device.register_callback(listener)
        self.client.update_callback(
            _shadow_response({"content": {"playing": "none"}}, version=2)
        )
        listener.assert_called_once_with()

    def test_repr_is_a_dict_with_the_raw_state(self):
        representation = self.device.__repr__()
        self.assertIsInstance(representation, dict)
        self.assertEqual(representation["shadow_state"], FULL_STATE)
        for attribute, _, _ in RESTORE_STATE_FIELDS:
            self.assertIn(attribute, representation)
        self.assertIs(representation["is_on"], True)


class RestoreProbeLoggingTest(unittest.TestCase):
    def test_logs_every_raw_report_as_json(self):
        device, client = _restore()
        with self.assertLogs("hatch_rest_api.restore", level="DEBUG") as logs:
            client.get_callback(_shadow_response(FULL_STATE))
        prefix = "restore raw shadow state for Bedroom: "
        raw = [
            record.getMessage()
            for record in logs.records
            if record.getMessage().startswith(prefix)
        ]
        self.assertEqual(len(raw), 1)
        self.assertEqual(json.loads(raw[0][len(prefix):]), FULL_STATE)


class RestoreWriteTest(unittest.TestCase):
    """The only writes known to work on this model, from homebridge-hatch-baby-rest."""

    def setUp(self):
        self.device, self.client = _restore()

    def test_turn_on_routine(self):
        self.device.turn_on_routine()
        self.assertEqual(
            self.client.published,
            [{"content": {"playing": "routine", "paused": False, "offset": 0, "step": 1}}],
        )

    def test_turn_on_routine_at_a_later_step(self):
        self.device.turn_on_routine(step=3)
        self.assertEqual(self.client.published[0]["content"]["step"], 3)

    def test_routine_steps_start_at_one(self):
        with self.assertRaises(ValueError):
            self.device.turn_on_routine(step=0)
        self.assertEqual(self.client.published, [])

    def test_turn_off(self):
        self.device.turn_off()
        self.assertEqual(
            self.client.published,
            [{"content": {"playing": "none", "paused": False, "offset": 0, "step": 0}}],
        )


class IotProductsTest(unittest.TestCase):
    def test_requests_the_original_restore(self):
        response = MagicMock()
        response.json = AsyncMock(return_value={"payload": []})
        api = Hatch(client_session=MagicMock())
        api._get_request_with_logging_and_errors_raised = AsyncMock(
            return_value=response
        )

        asyncio.run(api.iot_devices(auth_token="auth-token"))

        products = api._get_request_with_logging_and_errors_raised.call_args.kwargs[
            "params"
        ]["iotProducts"]
        self.assertIn("restore", products)
        self.assertIn("restoreIot", products)


if __name__ == "__main__":
    unittest.main()
