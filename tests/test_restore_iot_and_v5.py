"""RestoreIot (Restore 1st gen) and RestoreV5 read their shadow and build the expected updates.

The two classes share their light, favorite and volume code, so that is tested
against both (and RestoreV4, which is RestoreV5 under another name), followed by
the places where they differ.
"""

from typing import Any

import pytest

from hatch_rest_api import RestoreIot, RestoreV4, RestoreV5
from hatch_rest_api.const import (
    CUSTOM_COLOR_ID,
    NO_COLOR_ID,
    NO_SOUND_ID,
    RIOT_FLAGS_CLOCK_24_HOUR,
    RIOT_FLAGS_CLOCK_ON,
)
from hatch_rest_api.restore_v5 import pack_dual_percentages, unpack_dual_percentages
from hatch_rest_api.util import convert_from_hex, convert_from_percentage

from .device_fakes import FAVORITES, listener, recording_device, sent

RestoreDevice = RestoreIot | RestoreV5
ALL = pytest.mark.parametrize(
    "cls", [RestoreIot, RestoreV5, RestoreV4], ids=["RestoreIot", "RestoreV5", "RestoreV4"]
)

SOUND = {"id": 777, "title": "Rain", "wavUrl": "https://example.invalid/rain.wav"}

COMMON_STATE: dict[str, Any] = {
    "connected": True,
    "deviceInfo": {"f": "5.6.7"},
    "current": {
        "playing": "remote",
        "sound": {"id": 777, "v": 32768},
        "color": {"id": CUSTOM_COLOR_ID, "r": 65535, "g": 0, "b": 0, "w": 65535, "i": 49151},
    },
    "clock": {"flags": RIOT_FLAGS_CLOCK_ON | RIOT_FLAGS_CLOCK_24_HOUR},
}


# ---- shared behavior -----------------------------------------------------------


@ALL
def test_reads_reported_state(cls: type[RestoreDevice]) -> None:
    """Shadow fields map onto the device attributes and notify listeners."""
    device = recording_device(cls)
    device._update_local_state(COMMON_STATE)

    assert device.is_online is True
    assert device.firmware_version == "5.6.7"
    assert device.current_playing == "remote"
    assert device.volume == 50
    assert device.sound_id == 777
    assert device.color_id == CUSTOM_COLOR_ID
    assert (device.red, device.green, device.blue) == (255, 0, 0)
    # Unlike RestIot, the Restores scale white like the other channels.
    assert device.white == 255
    assert device.brightness == 75
    assert device.is_clock_on is True
    assert device.is_clock_24h is True
    assert device.is_light_on is True
    assert device.is_playing is True
    assert device.is_on is True
    listener(device).assert_called_once_with()


@ALL
def test_off_state(cls: type[RestoreDevice]) -> None:
    """No light, no sound and the clock flag clear read as off."""
    device = recording_device(cls, color_id=NO_COLOR_ID, sound_id=NO_SOUND_ID, flags=0)
    assert device.is_light_on is False
    assert device.is_playing is False
    assert device.is_on is False
    assert device.is_clock_on is False
    assert device.is_clock_24h is False


@ALL
def test_favorite_names(cls: type[RestoreDevice]) -> None:
    """Favorites are listed as name-id, active or not."""
    device = recording_device(cls, favorites=FAVORITES)
    assert device.favorite_names() == ["Bedtime-101", "Nap-102"]


@ALL
def test_set_favorite(cls: type[RestoreDevice]) -> None:
    """set_favorite starts the routine by the id after the last dash."""
    device = recording_device(cls)
    device.set_favorite("Bedtime-101")
    assert sent(device) == [{"current": {"srId": 101, "step": 1, "playing": "routine"}}]


@ALL
def test_set_volume(cls: type[RestoreDevice]) -> None:
    """set_volume sends the volume on the device's 16-bit scale."""
    device = recording_device(cls)
    device.set_volume(60)
    assert sent(device) == [{"current": {"sound": {"v": convert_from_percentage(60)}}}]


@ALL
def test_turn_off(cls: type[RestoreDevice]) -> None:
    """turn_off stops whatever is playing."""
    device = recording_device(cls)
    device.turn_off()
    assert sent(device) == [{"current": {"srId": 0, "step": 0, "playing": "none"}}]


@ALL
def test_turn_light_off_during_a_favorite_keeps_its_sound(cls: type[RestoreDevice]) -> None:
    """Turning the light off during a favorite only sends the color."""
    device = recording_device(cls, current_playing="routine")
    device.turn_light_off()
    assert sent(device) == [
        {"current": {"color": {"id": NO_COLOR_ID, "r": 0, "g": 0, "b": 0, "w": 0}}}
    ]


@ALL
def test_turn_light_off_with_nothing_playing_sends_nothing(cls: type[RestoreDevice]) -> None:
    """With nothing playing there is no light to turn off."""
    device = recording_device(cls, current_playing="none")
    device.turn_light_off()
    assert sent(device) == []


@ALL
def test_set_color_with_nothing_playing_takes_control(cls: type[RestoreDevice]) -> None:
    """With nothing playing, set_color also switches to remote playback."""
    device = recording_device(cls, current_playing="none")
    device.set_color(255, 0, 0, white=255, brightness=50)
    assert sent(device) == [
        {
            "current": {
                "srId": 0,
                "step": 0,
                "playing": "remote",
                "color": {
                    "id": CUSTOM_COLOR_ID,
                    "r": convert_from_hex(255),
                    "g": 0,
                    "b": 0,
                    "i": convert_from_percentage(50),
                    "w": convert_from_hex(255),
                },
            }
        }
    ]


@ALL
def test_set_color_while_playing_changes_only_the_color(cls: type[RestoreDevice]) -> None:
    """While something plays, set_color only sends the color."""
    device = recording_device(cls, current_playing="remote")
    device.set_color(0, 255, 0, brightness=20)
    assert list(sent(device)[0]["current"]) == ["color"]
    assert sent(device)[0]["current"]["color"]["g"] == convert_from_hex(255)


# ---- RestoreIot only -------------------------------------------------------------


def test_restore_iot_reads_clock_brightness() -> None:
    """RestoreIot's clock brightness is a single percentage."""
    device = recording_device(RestoreIot)
    device._update_local_state({"clock": {"i": 32768}})
    assert device.clock == 50


def test_restore_iot_set_clock() -> None:
    """RestoreIot's set_clock adds the clock-on flag and sends one brightness."""
    device = recording_device(RestoreIot, flags=RIOT_FLAGS_CLOCK_24_HOUR)
    device.set_clock(40)
    assert sent(device) == [
        {
            "clock": {
                "flags": RIOT_FLAGS_CLOCK_24_HOUR | RIOT_FLAGS_CLOCK_ON,
                "i": convert_from_percentage(40),
            }
        }
    ]


def test_restore_iot_turn_clock_off() -> None:
    """RestoreIot's turn_clock_off clears the clock-on flag."""
    device = recording_device(RestoreIot, flags=RIOT_FLAGS_CLOCK_24_HOUR | RIOT_FLAGS_CLOCK_ON)
    device.turn_clock_off()
    assert sent(device) == [{"clock": {"flags": RIOT_FLAGS_CLOCK_24_HOUR, "i": 655}}]


# ---- RestoreV5 only --------------------------------------------------------------


@pytest.mark.parametrize(("night", "day"), [(0, 0), (10, 90), (100, 100), (33, 67)])
def test_dual_percentages_round_trip(night: int, day: int) -> None:
    """The packed clock brightness round-trips both channels."""
    assert unpack_dual_percentages(pack_dual_percentages(night, day)) == (night, day)


def test_pack_puts_the_first_value_in_the_upper_half() -> None:
    """The first percentage is packed into the upper 16 bits."""
    assert pack_dual_percentages(100, 0) == 0xFFFF0000
    assert pack_dual_percentages(0, 100) == 0x0000FFFF


def test_restore_v5_reads_the_clock() -> None:
    """RestoreV5 unpacks night and day brightness and the clock schedule."""
    device = recording_device(RestoreV5)
    device._update_local_state(
        {
            "clock": {
                "i": pack_dual_percentages(20, 80),
                "turnOffMode": "custom",
                "turnOffAt": "22:00",
                "turnOnAt": "06:30",
                "turnDimAt": "20:00",
                "turnBrightAt": "07:00",
            },
            "current": {"srId": 5, "step": 3},
        }
    )
    assert (device.clock_nighttime, device.clock_daytime) == (20, 80)
    assert device.clock == 80
    assert device.clock_turn_off_mode == "custom"
    assert device.clock_turn_off_at == "22:00"
    assert device.clock_turn_on_at == "06:30"
    assert device.clock_turn_dim_at == "20:00"
    assert device.clock_turn_bright_at == "07:00"
    assert (device.current_id, device.current_step) == (5, 3)


def test_restore_v5_clock_before_brightness_is_reported() -> None:
    """Clock reads 0 until the device reports a brightness."""
    assert recording_device(RestoreV5).clock == 0


def test_restore_v5_set_clock_defaults_to_current_brightness() -> None:
    """set_clock with no arguments keeps the reported brightness."""
    device = recording_device(RestoreV5, clock_nighttime=10, clock_daytime=70, flags=0)
    device.set_clock()
    assert sent(device) == [
        {"clock": {"flags": RIOT_FLAGS_CLOCK_ON, "i": pack_dual_percentages(10, 70)}}
    ]


def test_restore_v5_set_clock_with_brightness() -> None:
    """set_clock packs the given night and day brightness."""
    device = recording_device(RestoreV5, flags=RIOT_FLAGS_CLOCK_24_HOUR)
    device.set_clock(daytime_brightness=90, nighttime_brightness=5)
    assert sent(device) == [
        {
            "clock": {
                "flags": RIOT_FLAGS_CLOCK_24_HOUR | RIOT_FLAGS_CLOCK_ON,
                "i": pack_dual_percentages(5, 90),
            }
        }
    ]


def test_restore_v5_turn_clock_off_keeps_brightness() -> None:
    """turn_clock_off clears the flag and re-sends the known brightness."""
    device = recording_device(
        RestoreV5,
        flags=RIOT_FLAGS_CLOCK_ON | RIOT_FLAGS_CLOCK_24_HOUR,
        clock_nighttime=10,
        clock_daytime=70,
    )
    device.turn_clock_off()
    assert sent(device) == [
        {"clock": {"flags": RIOT_FLAGS_CLOCK_24_HOUR, "i": pack_dual_percentages(10, 70)}}
    ]


def test_restore_v5_turn_clock_off_before_brightness_is_reported() -> None:
    """turn_clock_off doesn't zero the brightness before it has been reported."""
    device = recording_device(RestoreV5, flags=RIOT_FLAGS_CLOCK_ON)
    device.turn_clock_off()
    assert sent(device) == [{"clock": {"flags": 0}}]


@pytest.mark.parametrize("lookup", [777, "Rain", SOUND], ids=["id", "title", "dict"])
def test_restore_v5_set_sound(lookup: Any) -> None:
    """RestoreV5's set_sound accepts an id, a title or the sound itself."""
    device = recording_device(RestoreV5, sounds=[SOUND])
    device.set_sound(lookup, duration=60, until="duration")
    assert sent(device) == [
        {
            "current": {
                "playing": "remote",
                "sound": {
                    "id": 777,
                    "mute": False,
                    "url": "https://example.invalid/rain.wav",
                    "duration": 60,
                    "until": "duration",
                },
            }
        }
    ]


@pytest.mark.parametrize("none", [None, NO_SOUND_ID, "none"])
def test_restore_v5_set_sound_none_turns_off(none: Any) -> None:
    """set_sound with no sound turns the device off."""
    device = recording_device(RestoreV5)
    device.set_sound(none)
    assert sent(device) == [{"current": {"srId": 0, "step": 0, "playing": "none"}}]


def test_restore_v5_set_sound_unknown_sends_nothing() -> None:
    """An unknown sound is logged and nothing is sent."""
    device = recording_device(RestoreV5, sounds=[SOUND])
    device.set_sound("Unknown")
    assert sent(device) == []
