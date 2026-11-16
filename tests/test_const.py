"""Consistency checks for the hard-coded media URL maps."""

from enum import Enum

import pytest

from hatch_rest_api.const import (
    RestBabyAudioTrack,
    RIoTAudioTrack,
    TimeForBedTrack,
    TimeToRiseTrack,
)


def _track_values(enum: type[Enum]) -> set[int]:
    return {track.value for track in enum if track.name != "NONE"}


@pytest.mark.parametrize(
    ("enum", "url_map"),
    [
        (RIoTAudioTrack, RIoTAudioTrack.sound_url_map()),
        (RestBabyAudioTrack, RestBabyAudioTrack.sound_url_map()),
        (TimeToRiseTrack, TimeToRiseTrack.track_url_map()),
        (TimeForBedTrack, TimeForBedTrack.track_url_map()),
    ],
)
def test_url_map_covers_every_track(enum: type[Enum], url_map: dict[int, str]) -> None:
    """Every track except NONE has exactly one URL, and no URL maps to an unknown track."""
    assert set(url_map) == _track_values(enum)
