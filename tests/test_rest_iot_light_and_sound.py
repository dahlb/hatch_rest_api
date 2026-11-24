"""Tests that RestIot light and sound controls act independently."""

import unittest

from hatch_rest_api.const import CUSTOM_COLOR_ID, NO_COLOR_ID, NO_SOUND_ID, RIoTAudioTrack
from hatch_rest_api.rest_iot import RestIot
from hatch_rest_api.util import convert_from_hex, convert_from_percentage


def rest_iot(playing: str, light_on: bool, sound_on: bool) -> RestIot:
    """A RestIot in a given state whose shadow updates are recorded instead of sent."""
    device = RestIot.__new__(RestIot)
    device.device_name = "Rest"
    device.sent = []
    device._update = device.sent.append
    device.current_playing = playing
    device.color_id = CUSTOM_COLOR_ID if light_on else NO_COLOR_ID
    device.sound_id = RIoTAudioTrack.BrownNoise.value if sound_on else NO_SOUND_ID
    device.red, device.green, device.blue, device.white, device.brightness = (
        255,
        0,
        0,
        0,
        60,
    )
    return device


class TestLightAndSoundIndependent(unittest.TestCase):
    """Turning the light off keeps sound, and stopping sound keeps the light."""

    def test_light_off_keeps_a_remote_sound_playing(self) -> None:
        """Light off keeps a remote sound playing."""
        device = rest_iot("remote", light_on=True, sound_on=True)
        device.turn_light_off()
        assert len(device.sent) == 1
        current = device.sent[0]["current"]
        assert current["color"]["id"] == NO_COLOR_ID
        assert "playing" not in current

    def test_light_off_with_no_sound_turns_the_device_off(self) -> None:
        """Light off with no sound turns the device off."""
        device = rest_iot("remote", light_on=True, sound_on=False)
        device.turn_light_off()
        assert device.sent[0]["current"]["playing"] == "none"

    def test_light_off_during_a_favorite_keeps_its_sound(self) -> None:
        """Light off during a favorite keeps its sound."""
        device = rest_iot("routine", light_on=True, sound_on=True)
        device.turn_light_off()
        assert "playing" not in device.sent[0]["current"]

    def test_stop_sound_keeps_the_light_on(self) -> None:
        """Stop sound keeps the light on."""
        for playing in ("remote", "routine"):
            device = rest_iot(playing, light_on=True, sound_on=True)
            device.stop_sound()
            current = device.sent[0]["current"]
            # Manual control, so a favorite doesn't re-apply its sound, and the light as it was.
            assert current["playing"] == "remote"
            assert current["sound"]["id"] == NO_SOUND_ID
            assert current["color"]["id"] == CUSTOM_COLOR_ID
            assert current["color"]["r"] == convert_from_hex(255)
            assert current["color"]["i"] == convert_from_percentage(60)

    def test_stop_sound_with_no_light_turns_the_device_off(self) -> None:
        """Stop sound with no light turns the device off."""
        device = rest_iot("remote", light_on=False, sound_on=True)
        device.stop_sound()
        assert device.sent == [{"current": {"srId": 0, "step": 0, "playing": "none"}}]


if __name__ == "__main__":
    unittest.main()
