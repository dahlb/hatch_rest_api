"""RestPlus reads its shadow and builds the expected updates."""

from hatch_rest_api import RestPlus, RestPlusAudioTrack
from hatch_rest_api.util import convert_from_hex, convert_from_percentage

from .device_fakes import listener, recording_device, sent


def test_reads_reported_state() -> None:
    """Shadow fields map onto the device attributes and notify listeners."""
    device = recording_device(RestPlus)
    device._update_local_state(
        {
            "connected": True,
            "isPowered": True,
            "deviceInfo": {"f": "2.0.0", "b": 87},
            "a": {"t": RestPlusAudioTrack.Ocean.value, "v": 32768},
            "c": {"r": 65535, "g": 0, "b": 0, "i": 16384, "R": False, "W": False},
        }
    )

    assert device.is_online is True
    assert device.is_on is True
    assert device.firmware_version == "2.0.0"
    assert device.battery_level == 87
    assert device.audio_track is RestPlusAudioTrack.Ocean
    assert device.volume == 50
    assert (device.red, device.green, device.blue) == (255, 0, 0)
    assert device.brightness == 25
    assert device.is_playing is True
    listener(device).assert_called_once_with()


def test_black_without_random_or_white_reads_as_off() -> None:
    """An all-zero color with no random or white mode reports brightness 0."""
    device = recording_device(RestPlus)
    device._update_local_state({"c": {"r": 0, "g": 0, "b": 0, "i": 65535, "R": False, "W": False}})
    assert device.brightness == 0


def test_random_color_keeps_brightness() -> None:
    """Random color mode keeps the brightness even with an all-zero color."""
    device = recording_device(RestPlus)
    device._update_local_state({"c": {"r": 0, "g": 0, "b": 0, "i": 65535, "R": True, "W": False}})
    assert device.brightness == 100


def test_not_playing_when_off_or_silent() -> None:
    """is_playing needs the device on and a track selected."""
    assert not recording_device(
        RestPlus, is_on=False, audio_track=RestPlusAudioTrack.Ocean
    ).is_playing
    assert not recording_device(
        RestPlus, is_on=True, audio_track=RestPlusAudioTrack.NONE
    ).is_playing


def test_set_volume() -> None:
    """set_volume sends the volume on the device's 16-bit scale."""
    device = recording_device(RestPlus)
    device.set_volume(75)
    assert sent(device) == [{"a": {"v": convert_from_percentage(75)}}]


def test_set_audio_track() -> None:
    """set_audio_track sends the track id."""
    device = recording_device(RestPlus)
    device.set_audio_track(RestPlusAudioTrack.Dryer)
    assert sent(device) == [{"a": {"t": RestPlusAudioTrack.Dryer.value}}]


def test_set_on() -> None:
    """set_on toggles power."""
    device = recording_device(RestPlus)
    device.set_on(True)
    device.set_on(False)
    assert sent(device) == [{"isPowered": True}, {"isPowered": False}]


def test_set_color() -> None:
    """set_color scales channels and brightness and clears white mode."""
    device = recording_device(RestPlus)
    device.set_color(255, 128, 0, 60, random=True)
    assert sent(device) == [
        {
            "c": {
                "r": convert_from_hex(255),
                "g": convert_from_hex(128),
                "b": 0,
                "i": convert_from_percentage(60),
                "W": False,
                "R": True,
            }
        }
    ]
