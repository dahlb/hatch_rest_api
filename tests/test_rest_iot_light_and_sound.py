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
    device.red, device.green, device.blue, device.white, device.brightness = 255, 0, 0, 0, 60
    return device


class TestLightAndSoundIndependent(unittest.TestCase):
    def test_light_off_keeps_a_remote_sound_playing(self):
        device = rest_iot("remote", light_on=True, sound_on=True)
        device.turn_light_off()
        self.assertEqual(len(device.sent), 1)
        current = device.sent[0]["current"]
        self.assertEqual(current["color"]["id"], NO_COLOR_ID)
        self.assertNotIn("playing", current)

    def test_light_off_with_no_sound_turns_the_device_off(self):
        device = rest_iot("remote", light_on=True, sound_on=False)
        device.turn_light_off()
        self.assertEqual(device.sent[0]["current"]["playing"], "none")

    def test_light_off_during_a_favorite_keeps_its_sound(self):
        device = rest_iot("routine", light_on=True, sound_on=True)
        device.turn_light_off()
        self.assertNotIn("playing", device.sent[0]["current"])

    def test_stop_sound_keeps_the_light_on(self):
        for playing in ("remote", "routine"):
            device = rest_iot(playing, light_on=True, sound_on=True)
            device.stop_sound()
            current = device.sent[0]["current"]
            # Manual control, so a favorite doesn't re-apply its sound, and the light as it was.
            self.assertEqual(current["playing"], "remote")
            self.assertEqual(current["sound"]["id"], NO_SOUND_ID)
            self.assertEqual(current["color"]["id"], CUSTOM_COLOR_ID)
            self.assertEqual(current["color"]["r"], convert_from_hex(255))
            self.assertEqual(current["color"]["i"], convert_from_percentage(60))

    def test_stop_sound_with_no_light_turns_the_device_off(self):
        device = rest_iot("remote", light_on=False, sound_on=True)
        device.stop_sound()
        self.assertEqual(device.sent, [{"current": {"srId": 0, "step": 0, "playing": "none"}}])


if __name__ == "__main__":
    unittest.main()
