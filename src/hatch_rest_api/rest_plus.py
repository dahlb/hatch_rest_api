import logging

from .util import convert_to_percentage, safely_get_json_value, convert_from_percentage, convert_from_hex, convert_to_hex
from .shadow_client_subscriber import ShadowClientSubscriberMixin
from .const import RestPlusAudioTrack

_LOGGER = logging.getLogger(__name__)


class RestPlus(ShadowClientSubscriberMixin):
    firmware_version: str = None
    audio_track: int = None
    volume: int = None

    is_on: bool = None
    battery_level: int = None
    is_online: bool = None

    red: int = None
    green: int = None
    blue: int = None
    brightness: int = None

    def _update_local_state(self, state):
        _LOGGER.debug(f"update local state: {self.device_name}, {state}")
        self.firmware_version = safely_get_json_value(state, "deviceInfo.f")
        if safely_get_json_value(state, "a.t"):
            self.audio_track = RestPlusAudioTrack(
                safely_get_json_value(state, "a.t", int)
            )
        if safely_get_json_value(state, "a.v"):
            self.volume = convert_to_percentage(
                safely_get_json_value(state, "a.v", int)
            )
        if safely_get_json_value(state, "c"):
            self.red = convert_to_hex(safely_get_json_value(state, "c.r", int))
            self.green = convert_to_hex(safely_get_json_value(state, "c.g", int))
            self.blue = convert_to_hex(safely_get_json_value(state, "c.b", int))
            if (
                self.red == 0
                and self.green == 0
                and self.blue == 0
                and not safely_get_json_value(state, "c.R")
                and not safely_get_json_value(state, "c.W")
                or safely_get_json_value(state, "c.i", int) is None
            ):
                self.brightness = 0
            else:
                self.brightness = convert_to_percentage(
                    safely_get_json_value(state, "c.i", int)
                )
        self.battery_level = safely_get_json_value(state, "deviceInfo.b", int)
        self.is_on = safely_get_json_value(state, "isPowered", bool)
        self.is_online = safely_get_json_value(state, "connected", bool)
        self.publish_updates()

    @property
    def is_playing(self):
        return self.audio_track == RestPlusAudioTrack.NONE.value

    def __repr__(self):
        return {
            "device_name": self.device_name,
            "thing_name": self.thing_name,
            "firmware_version": self.firmware_version,
            "is_playing": self.is_playing,
            "audio_track": self.audio_track,
            "volume": self.volume,
            "is_on": self.is_on,
            "battery_level": self.battery_level,
            "is_online": self.is_online,
            "red": self.red,
            "green": self.green,
            "blue": self.blue,
            "brightness": self.brightness,
            "document_version": self.document_version,
        }

    def __str__(self):
        return f"{self.__repr__()}"

    def set_volume(self, percentage: int):
        self._update(
            {
                "a": {
                    "v": convert_from_percentage(percentage),
                },
            }
        )

    def set_audio_track(self, audio_track: RestPlusAudioTrack):
        self._update(
            {
                "a": {
                    "t": audio_track.value,
                },
            }
        )

    def set_on(self, on: bool):
        self._update({"isPowered": on})

    def set_color(self, red: int, green: int, blue: int, brightness: int):
        self._update(
            {
                "c": {
                    "r": convert_from_hex(red),
                    "g": convert_from_hex(green),
                    "b": convert_from_hex(blue),
                    "i": convert_from_percentage(brightness),
                    "W": False,
                    "R": False,
                }
            }
        )
