"""Hatch Rest Mini device."""

import logging
from typing import Any

from .const import RestMiniAudioTrack
from .shadow_client_subscriber import ShadowClientSubscriberMixin
from .util import convert_from_percentage, convert_to_percentage, safely_get_json_value

_LOGGER = logging.getLogger(__name__)


class RestMini(ShadowClientSubscriberMixin):
    """Hatch Rest Mini sound machine."""

    firmware_version: str = None
    is_online: bool = None

    audio_track: RestMiniAudioTrack = None
    volume: int = None

    current_playing: str = "none"

    def __repr__(self) -> str:
        """Return the device state as a dictionary for debugging."""
        return {
            "device_name": self.device_name,
            "thing_name": self.thing_name,
            "mac": self.mac,
            "is_online": self.is_online,
            "firmware_version": self.firmware_version,
            "is_playing": self.is_playing,
            "audio_track": self.audio_track,
            "volume": self.volume,
            "document_version": self.document_version,
        }

    def __str__(self) -> str:
        """Return the device state as a string."""
        return f"{self.__repr__()}"

    def _update_local_state(self, state: dict[str, Any]) -> None:
        _LOGGER.debug("update local state: %s, %s", self.device_name, state)
        if safely_get_json_value(state, "connected") is not None:
            self.is_online = safely_get_json_value(state, "connected")
        if safely_get_json_value(state, "deviceInfo.f") is not None:
            self.firmware_version = safely_get_json_value(state, "deviceInfo.f")
        if safely_get_json_value(state, "current.sound.id") is not None:
            self.audio_track = RestMiniAudioTrack(safely_get_json_value(state, "current.sound.id"))
        if safely_get_json_value(state, "current.playing") is not None:
            self.current_playing = safely_get_json_value(state, "current.playing")
        if safely_get_json_value(state, "current.sound.v") is not None:
            self.volume = convert_to_percentage(safely_get_json_value(state, "current.sound.v"))
        self.publish_updates()

    @property
    def is_playing(self) -> bool:
        """Whether a sound is currently playing."""
        return self.current_playing != "none"

    def set_volume(self, percentage: int) -> None:
        """Set the volume as a 0-100 percentage."""
        self._update(
            {
                "current": {
                    "sound": {
                        "v": convert_from_percentage(percentage),
                    },
                },
            }
        )

    def set_audio_track(self, audio_track: RestMiniAudioTrack) -> None:
        """Play ``audio_track``, or stop playback for ``RestMiniAudioTrack.NONE``."""
        if audio_track == RestMiniAudioTrack.NONE:
            self._update(
                {
                    "current": {
                        "playing": "none",
                        "step": 0,
                    },
                }
            )
        else:
            self._update(
                {
                    "current": {
                        "playing": "remote",
                        "step": 1,
                        "sound": {
                            "id": audio_track.value,
                            "until": "indefinite",
                        },
                    },
                }
            )
