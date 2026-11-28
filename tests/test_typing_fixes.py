"""Behavior covered by the strict mypy fixes."""

import asyncio
from typing import Any
import unittest
from unittest.mock import AsyncMock, MagicMock

from hatch_rest_api.const import RIOT_FLAGS_CLOCK_ON, RestPlusAudioTrack, RIoTAudioTrack
from hatch_rest_api.hatch import Hatch
from hatch_rest_api.rest_iot import RestIot
from hatch_rest_api.rest_plus import RestPlus


def recording_rest_iot(sounds: list[Any]) -> RestIot:
    """A RestIot whose shadow updates are recorded instead of sent."""
    device = RestIot.__new__(RestIot)
    device.device_name = "Rest"
    device.sounds = sounds
    device.sent = []
    device._update = device.sent.append
    return device


class RestIotClockFlagsTest(unittest.TestCase):
    """Clock controls work before the shadow has reported any flags."""

    def test_set_clock_without_reported_flags(self) -> None:
        """set_clock no longer fails on a None flags default."""
        device = recording_rest_iot([])
        device.set_clock(50)
        assert device.sent[0]["clock"]["flags"] == RIOT_FLAGS_CLOCK_ON

    def test_turn_clock_off_without_reported_flags(self) -> None:
        """turn_clock_off no longer fails on a None flags default."""
        device = recording_rest_iot([])
        device.turn_clock_off()
        assert device.sent[0]["clock"]["flags"] == RIOT_FLAGS_CLOCK_ON


class RestIotSoundUrlTest(unittest.TestCase):
    """API sounds without a URL do not replace the built-in URL."""

    def test_sound_without_wav_url_keeps_the_default(self) -> None:
        """A sound with a null wavUrl keeps the hard-coded URL."""
        track = RIoTAudioTrack.BrownNoise
        default_url = RIoTAudioTrack.sound_url_map()[track.value]
        device = recording_rest_iot([{"id": track.value, "title": "Brown", "wavUrl": None}])
        device.set_audio_track(track)
        assert device.sent[0]["current"]["sound"]["url"] == default_url

    def test_sound_with_wav_url_overrides_the_default(self) -> None:
        """A sound with a wavUrl still overrides the hard-coded URL."""
        track = RIoTAudioTrack.BrownNoise
        device = recording_rest_iot(
            [{"id": track.value, "title": "Brown", "wavUrl": "https://example.invalid/x.wav"}]
        )
        device.set_audio_track(track)
        assert device.sent[0]["current"]["sound"]["url"] == "https://example.invalid/x.wav"


class RestPlusIsPlayingTest(unittest.TestCase):
    """is_playing always returns a bool."""

    def test_unknown_power_state_is_not_playing(self) -> None:
        """is_playing is False, not None, before the power state is known."""
        device = RestPlus.__new__(RestPlus)
        device.is_on = None
        device.audio_track = RestPlusAudioTrack.Stream
        assert device.is_playing is False


class ScheduledRoutineOrderTest(unittest.TestCase):
    """Scheduled routines sort by displayOrder, with missing values last."""

    def test_null_display_order_sorts_last(self) -> None:
        """A null displayOrder no longer breaks the sort."""
        response = MagicMock()
        response.json = AsyncMock(
            return_value={
                "payload": [
                    {"id": 1, "displayOrder": None},
                    {"id": 2},
                    {"id": 3, "displayOrder": 2},
                    {"id": 4, "displayOrder": 1},
                ]
            }
        )
        api = Hatch(client_session=MagicMock())
        api._get_request_with_logging_and_errors_raised = AsyncMock(return_value=response)

        routines = asyncio.run(api.scheduled_routines(auth_token="token", mac="AA:BB"))

        assert [routine["id"] for routine in routines] == [4, 3, 1, 2]
