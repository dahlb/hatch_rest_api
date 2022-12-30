import logging

from .util import convert_to_percentage, safely_get_json_value, convert_from_percentage
from .shadow_client_subscriber import ShadowClientSubscriberMixin
from .const import RestMiniAudioTrack

_LOGGER = logging.getLogger(__name__)


class RestMini(ShadowClientSubscriberMixin):
    firmware_version: str = None
    is_online: bool = None

    is_playing: bool = None
    audio_track: RestMiniAudioTrack = None
    volume: int = None

    def __repr__(self):
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

    def __str__(self):
        return f"{self.__repr__()}"

    def _update_local_state(self, state):
        _LOGGER.debug(f"update local state: {self.device_name}, {state}")
        if safely_get_json_value(state, "connected") is not None:
            self.is_online = safely_get_json_value(state, "connected")
        if safely_get_json_value(state, "deviceInfo.f") is not None:
            self.firmware_version = safely_get_json_value(state, "deviceInfo.f")
        if safely_get_json_value(state, "current.sound.id") is not None:
            self.audio_track = RestMiniAudioTrack(
                safely_get_json_value(state, "current.sound.id")
            )
        if safely_get_json_value(state, "current.playing") is not None:
            self.is_playing = safely_get_json_value(state, "current.playing") != "none"
        if safely_get_json_value(state, "current.sound.v") is not None:
            self.volume = convert_to_percentage(
                safely_get_json_value(state, "current.sound.v")
            )
        self.publish_updates()

    def set_volume(self, percentage: int):
        self._update(
            {
                "current": {
                    "sound": {
                        "v": convert_from_percentage(percentage),
                    },
                },
            }
        )

    def set_audio_track(self, audio_track: RestMiniAudioTrack):
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
