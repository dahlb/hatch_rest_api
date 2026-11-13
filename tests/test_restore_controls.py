"""Original Restore light, sound, clock and alarm-switch writes.

Each payload here is one that was checked on a real device (docs/restore.md).
"""

import unittest
from concurrent.futures import Future
from datetime import time
from unittest.mock import MagicMock

from hatch_rest_api import Restore
from hatch_rest_api.const import RESTORE_COLORS, RESTORE_SOUNDS
from hatch_rest_api.util import convert_from_percentage

REMOTE = {"playing": "remote", "paused": False, "offset": 0, "step": 0}
STOP = {"playing": "none", "paused": False, "offset": 0, "step": 0}

IDLE_STATE = {
    "content": {"playing": "none", "step": 0},
    "sound": {"enabled": False, "id": 10040, "v": 0},
    "color": {"enabled": False, "id": 229, "i": 32767},
    "deviceDefaults": {"colorId": 229, "i": 32767, "soundId": 10040, "v": 0},
    "restoreClock": {
        "flags": 32768,
        "i": 2621,
        "turnOnAt": "07:00:00",
        "turnOffAt": "22:00:00",
        "turnOffMode": "never",
    },
    "alarmsDisabled": False,
}


def _done(result=None) -> Future:
    future: Future = Future()
    future.set_result(result)
    return future


class StubShadowClient:
    def __init__(self):
        self.published = []

    def subscribe_to_update_shadow_accepted(self, request, qos, callback):
        return _done(), "update-topic"

    def subscribe_to_get_shadow_accepted(self, request, qos, callback):
        return _done(), "get-topic"

    def publish_get_shadow(self, request, qos):
        return _done(MagicMock())

    def publish_update_shadow(self, request, qos):
        self.published.append(request.state.desired)
        return _done()


def _restore(state=None):
    client = StubShadowClient()
    device = Restore(
        device_name="Bedroom",
        thing_name="thing-1",
        mac="AA:BB:CC:DD:EE:FF",
        shadow_client=client,
    )
    device._update_local_state(state or IDLE_STATE)
    return device, client


def _playing(light: bool, sound: bool):
    return {
        "content": {"playing": "remote"},
        "color": {"enabled": light, "id": 218, "i": 45874},
        "sound": {"enabled": sound, "id": 10033, "v": 19660},
    }


class RestoreLightTest(unittest.TestCase):
    def test_light_on_while_idle_starts_remote_playback(self):
        # On its own a color write does nothing while nothing plays.
        device, client = _restore()
        device.turn_light_on()
        self.assertEqual(
            client.published,
            [
                {
                    "color": {"enabled": True, "id": 229, "i": convert_from_percentage(50)},
                    "content": REMOTE,
                    "sound": {"enabled": False},
                }
            ],
        )

    def test_light_on_while_playing_leaves_playback_alone(self):
        device, client = _restore()
        device._update_local_state(_playing(light=False, sound=True))
        device.turn_light_on(color_id=208, brightness=30)
        self.assertEqual(
            client.published,
            [{"color": {"enabled": True, "id": 208, "i": convert_from_percentage(30)}}],
        )

    def test_light_off_keeps_a_playing_sound(self):
        device, client = _restore()
        device._update_local_state(_playing(light=True, sound=True))
        device.turn_light_off()
        self.assertEqual(client.published, [{"color": {"enabled": False}}])

    def test_light_off_with_nothing_else_stops_playback(self):
        device, client = _restore()
        device._update_local_state(_playing(light=True, sound=False))
        device.turn_light_off()
        self.assertEqual(client.published, [{"content": STOP}])

    def test_brightness_and_color_while_on(self):
        device, client = _restore()
        device._update_local_state(_playing(light=True, sound=False))
        device.set_light_brightness(70)
        device.set_light_color(218)
        self.assertEqual(
            client.published,
            [{"color": {"i": convert_from_percentage(70)}}, {"color": {"id": 218}}],
        )

    def test_brightness_while_off_turns_the_light_on(self):
        device, client = _restore()
        device.set_light_brightness(20)
        self.assertEqual(client.published[0]["color"]["i"], convert_from_percentage(20))
        self.assertEqual(client.published[0]["content"], REMOTE)

    def test_state(self):
        device, _ = _restore()
        self.assertFalse(device.is_light_on)
        device._update_local_state(_playing(light=True, sound=False))
        self.assertTrue(device.is_light_on)
        self.assertFalse(device.is_sound_on)
        self.assertEqual(device.color_name, "Blue")
        self.assertEqual(device.brightness, 70)


class RestoreSoundTest(unittest.TestCase):
    def test_play_while_idle_starts_remote_playback_without_the_light(self):
        device, client = _restore()
        device.play_sound()
        self.assertEqual(
            client.published,
            [
                {
                    "sound": {"enabled": True, "id": 10040, "v": convert_from_percentage(25)},
                    "content": REMOTE,
                    "color": {"enabled": False},
                }
            ],
        )

    def test_remembers_the_volume_the_device_zeroes_on_stop(self):
        device, client = _restore()
        device._update_local_state(_playing(light=False, sound=True))  # 30%
        device._update_local_state({"content": {"playing": "none"}, "sound": {"enabled": False, "v": 0}})
        self.assertEqual(device.volume, 0)
        self.assertEqual(device.last_volume, 30)
        device.play_sound(sound_id=10033)
        self.assertEqual(client.published[0]["sound"]["v"], convert_from_percentage(30))

    def test_volume_and_sound_while_playing(self):
        device, client = _restore()
        device._update_local_state(_playing(light=False, sound=True))
        device.set_volume(15)
        device.set_sound(10019)
        self.assertEqual(
            client.published,
            [{"sound": {"v": convert_from_percentage(15)}}, {"sound": {"id": 10019}}],
        )

    def test_volume_while_idle_is_only_remembered(self):
        device, client = _restore()
        device.set_volume(40)
        self.assertEqual(client.published, [])
        self.assertEqual(device.last_volume, 40)

    def test_stop_keeps_a_light_that_is_on(self):
        device, client = _restore()
        device._update_local_state(_playing(light=True, sound=True))
        device.stop_sound()
        self.assertEqual(client.published, [{"sound": {"enabled": False}}])

    def test_stop_with_nothing_else_stops_playback(self):
        device, client = _restore()
        device._update_local_state(_playing(light=False, sound=True))
        device.stop_sound()
        self.assertEqual(client.published, [{"content": STOP}])

    def test_names(self):
        device, _ = _restore()
        device._update_local_state(_playing(light=True, sound=True))
        self.assertEqual(device.sound_name, "White Noise")
        self.assertEqual(len(RESTORE_SOUNDS), 31)
        self.assertEqual(len(RESTORE_COLORS), 22)


class RestoreClockTest(unittest.TestCase):
    def test_display_on_off_keeps_the_other_flags(self):
        device, client = _restore()
        device._update_local_state({"restoreClock": {"flags": 32768 | 2048}})
        device.set_clock(on=False)
        device._update_local_state({"restoreClock": {"flags": 2048}})
        device.set_clock(on=True, brightness=40)
        self.assertEqual(
            client.published,
            [
                {"restoreClock": {"flags": 2048}},
                {"restoreClock": {"flags": 32768 | 2048, "i": convert_from_percentage(40)}},
            ],
        )

    def test_24_hour(self):
        device, client = _restore()
        device.set_clock_24h(True)
        device._update_local_state({"restoreClock": {"flags": 34816}})
        device.set_clock_24h(False)
        self.assertEqual(
            client.published,
            [{"restoreClock": {"flags": 34816}}, {"restoreClock": {"flags": 32768}}],
        )
        self.assertTrue(device.is_clock_on)
        self.assertTrue(device.is_clock_24h)

    def test_night_schedule(self):
        device, client = _restore()
        device.set_clock_off_at_night(True)
        device.set_clock_off_at_night(False)
        device.set_clock_schedule(turn_on_at=time(6, 30), turn_off_at=time(21, 45))
        self.assertEqual(
            client.published,
            [
                {"restoreClock": {"turnOffMode": "custom"}},
                {"restoreClock": {"turnOffMode": "never"}},
                {"restoreClock": {"turnOnAt": "06:30:00", "turnOffAt": "21:45:00"}},
            ],
        )


class RestoreMiscTest(unittest.TestCase):
    def test_alarms_disabled(self):
        device, client = _restore()
        device.set_alarms_disabled(True)
        self.assertEqual(client.published, [{"alarmsDisabled": True}])

    def test_routine_steps_follow_the_routine_the_device_reports(self):
        device, _ = _restore()
        device.routines = [
            {"id": 1, "type": "routine", "steps": [{"name": "Read"}, {"name": "Sleep"}]},
            {"id": 2, "type": "routine", "steps": [{"name": "Wind Down "}, {}]},
        ]
        self.assertEqual(device.routine_steps, ["Read", "Sleep"])
        device._update_local_state({"content": {"routineId": 2}})
        self.assertEqual(device.routine_steps, ["Wind Down", "Step 2"])
        device.routines = None
        self.assertEqual(device.routine_steps, [])

    def test_repr_has_the_new_views(self):
        device, _ = _restore()
        representation = device.__repr__()
        for key in ("is_light_on", "is_sound_on", "color_name", "sound_name", "last_volume", "restore_alarms"):
            self.assertIn(key, representation)
        self.assertEqual(representation["default_color_id"], 229)


if __name__ == "__main__":
    unittest.main()
