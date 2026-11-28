"""RestIot (Rest 2nd gen) and RestBaby read their shadow and build the expected updates.

The two classes share most of their code, so the shared behavior is tested
against both, followed by the places where they differ.
"""

from typing import Any

import pytest

from hatch_rest_api import RestBaby, RestBabyAudioTrack, RestIot, RIoTAudioTrack
from hatch_rest_api.const import (
    CUSTOM_COLOR_ID,
    NO_COLOR_ID,
    NO_SOUND_ID,
    RIOT_FLAGS_CLOCK_24_HOUR,
    RIOT_FLAGS_CLOCK_ON,
)
from hatch_rest_api.util import convert_from_hex, convert_from_percentage

from .device_fakes import FAVORITES, listener, recording_device, sent

BOTH = pytest.mark.parametrize("cls", [RestIot, RestBaby], ids=["RestIot", "RestBaby"])

SOUND = {"id": 555, "title": "Rain", "wavUrl": "https://example.invalid/rain.wav"}
MP3_SOUND = {"id": 556, "title": "Waves", "wavUrl": None, "mp3Url": "https://example.invalid/w.mp3"}

REPORTED_STATE: dict[str, Any] = {
    "connected": True,
    "toddlerLockOn": True,
    "toddlerLock": {"turnOnMode": "always"},
    "deviceInfo": {"f": "3.4.5", "b": 64, "powerStatus": 3},
    "current": {
        "playing": "routine",
        "srId": 101,
        "step": 2,
        "sound": {"id": 10200, "v": 32768},
        "color": {"id": CUSTOM_COLOR_ID, "r": 65535, "g": 0, "b": 65535, "w": 7, "i": 16384},
    },
    "clock": {"i": 65535, "flags": RIOT_FLAGS_CLOCK_ON | RIOT_FLAGS_CLOCK_24_HOUR},
}


# ---- shared behavior -----------------------------------------------------------


@BOTH
def test_reads_reported_state(cls: type[RestIot | RestBaby]) -> None:
    """Shadow fields map onto the device attributes and notify listeners."""
    device = recording_device(cls)
    device._update_local_state(REPORTED_STATE)

    assert device.is_online is True
    assert device.firmware_version == "3.4.5"
    assert device.battery_level == 64
    assert device.charging_status == 3
    assert device.toddler_lock is True
    assert device.toddler_lock_mode == "always"
    assert device.current_playing == "routine"
    assert device.current_id == 101
    assert device.current_step == 2
    assert device.volume == 50
    assert device.sound_id == 10200
    assert device.color_id == CUSTOM_COLOR_ID
    assert (device.red, device.green, device.blue) == (255, 0, 255)
    assert device.white == 7
    assert device.brightness == 25
    assert device.clock == 100
    assert device.is_clock_on is True
    assert device.is_light_on is True
    assert device.is_playing is True
    assert device.is_on is True
    listener(device).assert_called_once_with()


def test_rest_iot_maps_known_sound_to_track() -> None:
    """A RestIot sound id that matches a track sets audio_track."""
    device = recording_device(RestIot)
    device._update_local_state({"current": {"sound": {"id": RIoTAudioTrack.BrownNoise.value}}})
    assert device.audio_track is RIoTAudioTrack.BrownNoise


@BOTH
def test_unknown_sound_id_keeps_the_track(cls: type[RestIot | RestBaby]) -> None:
    """A sound id outside the track enum updates sound_id but not audio_track."""
    device = recording_device(cls)
    device._update_local_state({"current": {"sound": {"id": 999_999}}})
    assert device.sound_id == 999_999
    assert device.audio_track is None


@BOTH
def test_off_state(cls: type[RestIot | RestBaby]) -> None:
    """No light, no sound and the clock flag clear read as off."""
    device = recording_device(cls, color_id=NO_COLOR_ID, sound_id=NO_SOUND_ID, flags=0)
    assert device.is_light_on is False
    assert device.is_playing is False
    assert device.is_on is False
    assert device.is_clock_on is False


@BOTH
def test_favorite_names(cls: type[RestIot | RestBaby]) -> None:
    """Favorites are listed as name-id, active or not."""
    device = recording_device(cls, favorites=FAVORITES)
    assert device.favorite_names() == ["Bedtime-101", "Nap-102"]
    assert device.favorite_names(active_only=False) == ["Bedtime-101", "Nap-102"]


@BOTH
def test_set_favorite(cls: type[RestIot | RestBaby]) -> None:
    """set_favorite starts the routine by the id after the last dash."""
    device = recording_device(cls)
    device.set_favorite("Wind-down - quiet-102")
    assert sent(device) == [{"current": {"srId": 102, "step": 1, "playing": "routine"}}]


@BOTH
def test_set_volume(cls: type[RestIot | RestBaby]) -> None:
    """set_volume sends the volume on the device's 16-bit scale."""
    device = recording_device(cls)
    device.set_volume(40)
    assert sent(device) == [{"current": {"sound": {"v": convert_from_percentage(40)}}}]


@BOTH
@pytest.mark.parametrize(("on", "mode"), [(True, "always"), (False, "never")])
def test_set_toddler_lock(cls: type[RestIot | RestBaby], on: bool, mode: str) -> None:
    """set_toddler_lock switches the lock mode."""
    device = recording_device(cls)
    device.set_toddler_lock(on)
    assert sent(device) == [{"toddlerLock": {"turnOnMode": mode}}]


@BOTH
def test_set_clock_keeps_other_flags(cls: type[RestIot | RestBaby]) -> None:
    """set_clock adds the clock-on flag to the flags already set."""
    device = recording_device(cls, flags=RIOT_FLAGS_CLOCK_24_HOUR)
    device.set_clock(30)
    assert sent(device) == [
        {
            "clock": {
                "flags": RIOT_FLAGS_CLOCK_24_HOUR | RIOT_FLAGS_CLOCK_ON,
                "i": convert_from_percentage(30),
            }
        }
    ]


@BOTH
def test_turn_clock_off(cls: type[RestIot | RestBaby]) -> None:
    """turn_clock_off clears the clock-on flag and keeps the others."""
    device = recording_device(cls, flags=RIOT_FLAGS_CLOCK_24_HOUR | RIOT_FLAGS_CLOCK_ON)
    device.turn_clock_off()
    assert sent(device) == [{"clock": {"flags": RIOT_FLAGS_CLOCK_24_HOUR, "i": 655}}]


@BOTH
def test_turn_off(cls: type[RestIot | RestBaby]) -> None:
    """turn_off stops whatever is playing."""
    device = recording_device(cls)
    device.turn_off()
    assert sent(device) == [{"current": {"srId": 0, "step": 0, "playing": "none"}}]


@BOTH
@pytest.mark.parametrize("none", [None, NO_SOUND_ID, "none"])
def test_set_sound_none_turns_off(cls: type[RestIot | RestBaby], none: Any) -> None:
    """set_sound with no sound turns the device off."""
    device = recording_device(cls)
    device.set_sound(none)
    assert sent(device) == [{"current": {"srId": 0, "step": 0, "playing": "none"}}]


@BOTH
@pytest.mark.parametrize("lookup", [555, "Rain", SOUND], ids=["id", "title", "dict"])
def test_set_sound_finds_the_sound(cls: type[RestIot | RestBaby], lookup: Any) -> None:
    """set_sound accepts an id, a title or the sound itself."""
    device = recording_device(cls, sounds=[SOUND])
    device.set_sound(lookup, duration=30, until="duration")
    sound = sent(device)[0]["current"]["sound"]
    assert sent(device)[0]["current"]["playing"] == "remote"
    assert (sound["id"], sound["url"], sound["duration"], sound["until"], sound["mute"]) == (
        555,
        "https://example.invalid/rain.wav",
        30,
        "duration",
        False,
    )


@BOTH
def test_set_sound_falls_back_to_mp3(cls: type[RestIot | RestBaby]) -> None:
    """A sound with no wavUrl plays its mp3Url."""
    device = recording_device(cls, sounds=[MP3_SOUND])
    device.set_sound(556)
    assert sent(device)[0]["current"]["sound"]["url"] == "https://example.invalid/w.mp3"


@BOTH
@pytest.mark.parametrize(
    "missing",
    [12345, "Unknown", {"id": 1}, {"wavUrl": "x"}],
    ids=["id", "title", "no-url", "no-id"],
)
def test_set_sound_unknown_sends_nothing(cls: type[RestIot | RestBaby], missing: Any) -> None:
    """An unknown or incomplete sound is logged and nothing is sent."""
    device = recording_device(cls, sounds=[SOUND])
    device.set_sound(missing)
    assert sent(device) == []


@BOTH
def test_set_audio_track_none_turns_off(cls: type[RestIot | RestBaby]) -> None:
    """set_audio_track(NONE) turns the device off."""
    device = recording_device(cls)
    track = RIoTAudioTrack.NONE if cls is RestIot else RestBabyAudioTrack.NONE
    device.set_audio_track(track)  # type: ignore[arg-type]
    assert sent(device) == [{"current": {"srId": 0, "step": 0, "playing": "none"}}]


@BOTH
def test_set_color_with_nothing_playing_takes_control(cls: type[RestIot | RestBaby]) -> None:
    """With nothing playing, set_color also switches to remote playback."""
    device = recording_device(cls, current_playing="none")
    device.set_color(255, 0, 0, white=5, brightness=50)
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
                    "w": 5,
                },
            }
        }
    ]


@BOTH
def test_set_color_while_playing_changes_only_the_color(cls: type[RestIot | RestBaby]) -> None:
    """While something plays, set_color only sends the color."""
    device = recording_device(cls, current_playing="routine")
    device.set_color(0, 0, 255, brightness=10)
    assert sent(device) == [
        {
            "current": {
                "color": {
                    "id": CUSTOM_COLOR_ID,
                    "r": 0,
                    "g": 0,
                    "b": convert_from_hex(255),
                    "i": convert_from_percentage(10),
                    "w": 0,
                }
            }
        }
    ]


@BOTH
def test_turn_light_off_during_a_favorite_keeps_its_sound(cls: type[RestIot | RestBaby]) -> None:
    """Turning the light off during a favorite only sends the color."""
    device = recording_device(cls, current_playing="routine")
    device.turn_light_off()
    assert sent(device) == [
        {"current": {"color": {"id": NO_COLOR_ID, "r": 0, "g": 0, "b": 0, "w": 0}}}
    ]


@BOTH
def test_set_sound_url(cls: type[RestIot | RestBaby]) -> None:
    """set_sound_url plays a URL directly."""
    device = recording_device(cls)
    device.set_sound_url("https://example.invalid/x.mp3")
    current = sent(device)[0]["current"]
    assert current["playing"] == "remote"
    assert current["sound"]["url"] == "https://example.invalid/x.mp3"
    assert current["sound"]["mute"] is False


# ---- RestIot only ----------------------------------------------------------------


def test_rest_iot_24h_clock() -> None:
    """RestIot reads the 24-hour flag."""
    assert recording_device(RestIot, flags=RIOT_FLAGS_CLOCK_24_HOUR).is_clock_24h is True
    assert recording_device(RestIot, flags=RIOT_FLAGS_CLOCK_ON).is_clock_24h is False


def test_rest_iot_set_audio_track() -> None:
    """RestIot plays a track from its built-in URL map at step 1."""
    device = recording_device(RestIot)
    device.set_audio_track(RIoTAudioTrack.BrownNoise)
    assert sent(device) == [
        {
            "current": {
                "playing": "remote",
                "step": 1,
                "sound": {
                    "id": RIoTAudioTrack.BrownNoise.value,
                    "url": RIoTAudioTrack.sound_url_map()[RIoTAudioTrack.BrownNoise.value],
                    "mute": False,
                    "until": "indefinite",
                },
            }
        }
    ]


# ---- RestBaby only ---------------------------------------------------------------


def test_rest_baby_set_audio_track_sends_volume() -> None:
    """RestBaby plays at step 0 and sends the current volume with the track."""
    track = RestBabyAudioTrack.Birds
    device = recording_device(RestBaby, volume=35)
    device.set_audio_track(track)
    assert sent(device) == [
        {
            "current": {
                "playing": "remote",
                "step": 0,
                "sound": {
                    "id": track.value,
                    "url": RestBabyAudioTrack.sound_url_map()[track.value],
                    "mute": False,
                    "until": "indefinite",
                    "duration": 0,
                    "v": convert_from_percentage(35),
                },
            }
        }
    ]


def test_rest_baby_set_audio_track_with_volume() -> None:
    """RestBaby's set_audio_track can override the volume."""
    device = recording_device(RestBaby, volume=35)
    device.set_audio_track(RestBabyAudioTrack.Birds, volume=80)
    assert sent(device)[0]["current"]["sound"]["v"] == convert_from_percentage(80)


def test_rest_baby_set_sound_sends_volume() -> None:
    """RestBaby's set_sound also sends the current volume."""
    device = recording_device(RestBaby, sounds=[SOUND], volume=20)
    device.set_sound(555)
    assert sent(device)[0]["current"]["step"] == 0
    assert sent(device)[0]["current"]["sound"]["v"] == convert_from_percentage(20)


@pytest.mark.parametrize("method", ["set_clock", "turn_clock_off"])
def test_rest_baby_clock_before_flags_are_reported(method: str) -> None:
    """RestBaby's clock controls work before the shadow reports any flags."""
    device = recording_device(RestBaby, flags=None)
    getattr(device, method)()
    assert sent(device)[0]["clock"]["flags"] == RIOT_FLAGS_CLOCK_ON
