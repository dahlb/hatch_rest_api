"""turn_light_off keeps a playing sound, and favorite_names filters by active_only.

RestIot already behaved this way; RestBaby, RestoreIot and RestoreV5 used to
stop a sound started from the app (``playing: remote``) when turning the light off.
"""

import pytest

from hatch_rest_api import RestBaby, RestIot, RestoreIot, RestoreV4, RestoreV5
from hatch_rest_api.const import CUSTOM_COLOR_ID, NO_COLOR_ID, NO_SOUND_ID

from .device_fakes import FAVORITES, recording_device, sent

LightDevice = RestIot | RestBaby | RestoreIot | RestoreV5
ALL = pytest.mark.parametrize(
    "cls",
    [RestIot, RestBaby, RestoreIot, RestoreV5, RestoreV4],
    ids=["RestIot", "RestBaby", "RestoreIot", "RestoreV5", "RestoreV4"],
)

COLOR_OFF = {"id": NO_COLOR_ID, "r": 0, "g": 0, "b": 0, "w": 0}


@ALL
def test_light_off_keeps_a_remote_sound_playing(cls: type[LightDevice]) -> None:
    """With a sound started from the app, only the light is turned off."""
    device = recording_device(
        cls, current_playing="remote", sound_id=12345, color_id=CUSTOM_COLOR_ID
    )
    device.turn_light_off()
    assert sent(device) == [{"current": {"color": COLOR_OFF}}]


@ALL
def test_light_off_with_no_sound_turns_the_device_off(cls: type[LightDevice]) -> None:
    """With only the light on, turning it off stops remote playback."""
    device = recording_device(
        cls, current_playing="remote", sound_id=NO_SOUND_ID, color_id=CUSTOM_COLOR_ID
    )
    device.turn_light_off()
    assert sent(device) == [{"current": {"playing": "none", "color": COLOR_OFF}}]


@ALL
def test_light_off_during_a_favorite_keeps_its_sound(cls: type[LightDevice]) -> None:
    """During a favorite, only the light is turned off."""
    device = recording_device(cls, current_playing="routine", sound_id=12345)
    device.turn_light_off()
    assert sent(device) == [{"current": {"color": COLOR_OFF}}]


@ALL
def test_light_off_with_nothing_playing_sends_nothing(cls: type[LightDevice]) -> None:
    """With nothing playing there is no light to turn off."""
    device = recording_device(cls, current_playing="none")
    device.turn_light_off()
    assert sent(device) == []


@ALL
def test_favorite_names_lists_every_favorite_by_default(cls: type[LightDevice]) -> None:
    """With no argument every favorite is listed, as before."""
    device = recording_device(cls, favorites=FAVORITES)
    assert device.favorite_names() == ["Bedtime-101", "Nap-102"]
    assert device.favorite_names(active_only=False) == ["Bedtime-101", "Nap-102"]


@ALL
def test_favorite_names_active_only(cls: type[LightDevice]) -> None:
    """active_only=True leaves out favorites that aren't active, or don't say."""
    favorites = [*FAVORITES, {"id": 103, "name": "Unknown"}]
    device = recording_device(cls, favorites=favorites)
    assert device.favorite_names(active_only=True) == ["Bedtime-101"]
