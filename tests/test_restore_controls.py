"""Original Restore light, sound, clock and alarm-switch writes.

Each payload here is one that was checked on a real device (docs/restore.md).
"""

from collections.abc import Callable
from concurrent.futures import Future
from datetime import time
from typing import Any
import unittest
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


def _done(result: Any = None) -> Future:
    """Return a future that has already resolved to ``result``."""
    future: Future = Future()
    future.set_result(result)
    return future


class StubShadowClient:
    """IotShadowClient stub that records every desired state sent."""

    def __init__(self) -> None:
        """Start with nothing published."""
        self.published: list[dict[str, Any]] = []

    def subscribe_to_update_shadow_accepted(
        self, request: Any, qos: Any, callback: Callable[[Any], None]
    ) -> tuple[Future, str]:
        """Accept the subscription."""
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
        """Record the desired state sent."""
        self.published.append(request.state.desired)
        return _done()


def _restore(state: dict[str, Any] | None = None) -> tuple[Restore, StubShadowClient]:
    """Build a Restore that has reported ``state``, by default an idle one."""
    client = StubShadowClient()
    device = Restore(
        device_name="Bedroom",
        thing_name="thing-1",
        mac="AA:BB:CC:DD:EE:FF",
        shadow_client=client,
    )
    device._update_local_state(state or IDLE_STATE)
    return device, client


def _playing(light: bool, sound: bool) -> dict[str, Any]:
    """A report of remote playback with the light and/or sound on."""
    return {
        "content": {"playing": "remote"},
        "color": {"enabled": light, "id": 218, "i": 45874},
        "sound": {"enabled": sound, "id": 10033, "v": 19660},
    }


class RestoreLightTest(unittest.TestCase):
    """Light writes."""

    def test_light_on_while_idle_starts_remote_playback(self) -> None:
        """Light on while idle starts remote playback."""
        # On its own a color write does nothing while nothing plays.
        device, client = _restore()
        device.turn_light_on()
        assert client.published == [
            {
                "color": {"enabled": True, "id": 229, "i": convert_from_percentage(50)},
                "content": REMOTE,
                "sound": {"enabled": False},
            }
        ]

    def test_light_on_while_playing_leaves_playback_alone(self) -> None:
        """Light on while playing leaves playback alone."""
        device, client = _restore()
        device._update_local_state(_playing(light=False, sound=True))
        device.turn_light_on(color_id=208, brightness=30)
        assert client.published == [
            {"color": {"enabled": True, "id": 208, "i": convert_from_percentage(30)}}
        ]

    def test_light_off_keeps_a_playing_sound(self) -> None:
        """Light off keeps a playing sound."""
        device, client = _restore()
        device._update_local_state(_playing(light=True, sound=True))
        device.turn_light_off()
        assert client.published == [{"color": {"enabled": False}}]

    def test_light_off_with_nothing_else_stops_playback(self) -> None:
        """Light off with nothing else stops playback."""
        device, client = _restore()
        device._update_local_state(_playing(light=True, sound=False))
        device.turn_light_off()
        assert client.published == [{"content": STOP}]

    def test_brightness_and_color_while_on(self) -> None:
        """Brightness and color while on."""
        device, client = _restore()
        device._update_local_state(_playing(light=True, sound=False))
        device.set_light_brightness(70)
        device.set_light_color(218)
        assert client.published == [
            {"color": {"i": convert_from_percentage(70)}},
            {"color": {"id": 218}},
        ]

    def test_brightness_while_off_turns_the_light_on(self) -> None:
        """Brightness while off turns the light on."""
        device, client = _restore()
        device.set_light_brightness(20)
        assert client.published[0]["color"]["i"] == convert_from_percentage(20)
        assert client.published[0]["content"] == REMOTE

    def test_state(self) -> None:
        """State."""
        device, _ = _restore()
        assert not device.is_light_on
        device._update_local_state(_playing(light=True, sound=False))
        assert device.is_light_on
        assert not device.is_sound_on
        assert device.color_name == "Blue"
        assert device.brightness == 70


class RestoreSoundTest(unittest.TestCase):
    """Sound writes."""

    def test_play_while_idle_starts_remote_playback_without_the_light(self) -> None:
        """Play while idle starts remote playback without the light."""
        device, client = _restore()
        device.play_sound()
        assert client.published == [
            {
                "sound": {"enabled": True, "id": 10040, "v": convert_from_percentage(25)},
                "content": REMOTE,
                "color": {"enabled": False},
            }
        ]

    def test_remembers_the_volume_the_device_zeroes_on_stop(self) -> None:
        """Remembers the volume the device zeroes on stop."""
        device, client = _restore()
        device._update_local_state(_playing(light=False, sound=True))  # 30%
        device._update_local_state(
            {"content": {"playing": "none"}, "sound": {"enabled": False, "v": 0}}
        )
        assert device.volume == 0
        assert device.last_volume == 30
        device.play_sound(sound_id=10033)
        assert client.published[0]["sound"]["v"] == convert_from_percentage(30)

    def test_volume_and_sound_while_playing(self) -> None:
        """Volume and sound while playing."""
        device, client = _restore()
        device._update_local_state(_playing(light=False, sound=True))
        device.set_volume(15)
        device.set_sound(10019)
        assert client.published == [
            {"sound": {"v": convert_from_percentage(15)}},
            {"sound": {"id": 10019}},
        ]

    def test_volume_while_idle_is_only_remembered(self) -> None:
        """Volume while idle is only remembered."""
        device, client = _restore()
        device.set_volume(40)
        assert client.published == []
        assert device.last_volume == 40

    def test_stop_keeps_a_light_that_is_on(self) -> None:
        """Stop keeps a light that is on."""
        device, client = _restore()
        device._update_local_state(_playing(light=True, sound=True))
        device.stop_sound()
        assert client.published == [{"sound": {"enabled": False}}]

    def test_stop_with_nothing_else_stops_playback(self) -> None:
        """Stop with nothing else stops playback."""
        device, client = _restore()
        device._update_local_state(_playing(light=False, sound=True))
        device.stop_sound()
        assert client.published == [{"content": STOP}]

    def test_names(self) -> None:
        """Names."""
        device, _ = _restore()
        device._update_local_state(_playing(light=True, sound=True))
        assert device.sound_name == "White Noise"
        assert len(RESTORE_SOUNDS) == 31
        assert len(RESTORE_COLORS) == 22


class RestoreClockTest(unittest.TestCase):
    """Clock display writes."""

    def test_display_on_off_keeps_the_other_flags(self) -> None:
        """Display on off keeps the other flags."""
        device, client = _restore()
        device._update_local_state({"restoreClock": {"flags": 32768 | 2048}})
        device.set_clock(on=False)
        device._update_local_state({"restoreClock": {"flags": 2048}})
        device.set_clock(on=True, brightness=40)
        assert client.published == [
            {"restoreClock": {"flags": 2048}},
            {"restoreClock": {"flags": 32768 | 2048, "i": convert_from_percentage(40)}},
        ]

    def test_24_hour(self) -> None:
        """24 hour."""
        device, client = _restore()
        device.set_clock_24h(True)
        device._update_local_state({"restoreClock": {"flags": 34816}})
        device.set_clock_24h(False)
        assert client.published == [
            {"restoreClock": {"flags": 34816}},
            {"restoreClock": {"flags": 32768}},
        ]
        assert device.is_clock_on
        assert device.is_clock_24h

    def test_night_schedule(self) -> None:
        """Night schedule."""
        device, client = _restore()
        device.set_clock_off_at_night(True)
        device.set_clock_off_at_night(False)
        device.set_clock_schedule(turn_on_at=time(6, 30), turn_off_at=time(21, 45))
        assert client.published == [
            {"restoreClock": {"turnOffMode": "custom"}},
            {"restoreClock": {"turnOffMode": "never"}},
            {"restoreClock": {"turnOnAt": "06:30:00", "turnOffAt": "21:45:00"}},
        ]


class RestoreMiscTest(unittest.TestCase):
    """The all-alarms switch, routine steps and the debug view."""

    def test_alarms_disabled(self) -> None:
        """Alarms disabled."""
        device, client = _restore()
        device.set_alarms_disabled(True)
        assert client.published == [{"alarmsDisabled": True}]

    def test_routine_steps_follow_the_routine_the_device_reports(self) -> None:
        """Routine steps follow the routine the device reports."""
        device, _ = _restore()
        device.routines = [
            {"id": 1, "type": "routine", "steps": [{"name": "Read"}, {"name": "Sleep"}]},
            {"id": 2, "type": "routine", "steps": [{"name": "Wind Down "}, {}]},
        ]
        assert device.routine_steps == ["Read", "Sleep"]
        device._update_local_state({"content": {"routineId": 2}})
        assert device.routine_steps == ["Wind Down", "Step 2"]
        device.routines = None
        assert device.routine_steps == []

    def test_as_dict_has_the_new_views(self) -> None:
        """as_dict has the new views."""
        device, _ = _restore()
        representation = device.as_dict()
        for key in (
            "is_light_on",
            "is_sound_on",
            "color_name",
            "sound_name",
            "last_volume",
            "restore_alarms",
        ):
            assert key in representation
        assert representation["default_color_id"] == 229


if __name__ == "__main__":
    unittest.main()
