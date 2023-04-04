import logging

from .util import (
    convert_to_percentage,
    safely_get_json_value,
    convert_from_percentage,
    convert_from_hex,
    convert_to_hex,
)
from .const import RIOT_FLAGS_CLOCK_ON, RIOT_FLAGS_CLOCK_24_HOUR
from .shadow_client_subscriber import ShadowClientSubscriberMixin

_LOGGER = logging.getLogger(__name__)


class RestoreIot(ShadowClientSubscriberMixin):
    audio_track: str = None
    firmware_version: str = None
    volume: int = 0

    is_online: bool = False
    current_playing: str = "none"

    color_id: int = 9998
    sound_id: int = 19998
    red: int = 0
    green: int = 0
    blue: int = 0
    white: int = 0
    brightness: int = 0
    charging_status: int = None  # Expected values: 0= Not Charging, 3= Charging, plugged in, 5= Charging, on base
    clock: int = 0
    flags: int = 0

    is_on: bool = None

    def _update_local_state(self, state):
        _LOGGER.debug(f"update local state: {self.device_name}, {state}")
        if safely_get_json_value(state, "deviceInfo.f") is not None:
            self.firmware_version = safely_get_json_value(state, "deviceInfo.f")

        if safely_get_json_value(state, "current.playing") is not None:
            self.current_playing = safely_get_json_value(state, "current.playing")
        if safely_get_json_value(state, "connected") is not None:
            self.is_online = safely_get_json_value(state, "connected", bool)
        if safely_get_json_value(state, "current.sound.v") is not None:
            self.volume = convert_to_percentage(
                safely_get_json_value(state, "current.sound.v", int)
            )
        if safely_get_json_value(state, "current.sound.id", int) is not None:
            self.sound_id = safely_get_json_value(state, "current.sound.id", int)
        if safely_get_json_value(state, "current.color.id") is not None:
            self.color_id = safely_get_json_value(state, "current.color.id", int)
        if safely_get_json_value(state, "current.color.r") is not None:
            self.red = convert_to_hex(
                safely_get_json_value(state, "current.color.r", int)
            )
        if safely_get_json_value(state, "current.color.g") is not None:
            self.green = convert_to_hex(
                safely_get_json_value(state, "current.color.g", int)
            )
        if safely_get_json_value(state, "current.color.b") is not None:
            self.blue = convert_to_hex(
                safely_get_json_value(state, "current.color.b", int)
            )
        if safely_get_json_value(state, "current.color.w") is not None:
            self.white = convert_to_hex(
                safely_get_json_value(state, "current.color.w", int)
            )
        if safely_get_json_value(state, "current.color.i") is not None:
            self.brightness = convert_to_percentage(
                safely_get_json_value(state, "current.color.i", int)
            )
        if safely_get_json_value(state, "clock.i") is not None:
            self.clock = convert_to_percentage(
                safely_get_json_value(state, "clock.i", int)
            )
        if safely_get_json_value(state, "clock.flags") is not None:
            self.flags = safely_get_json_value(state, "clock.flags", int)

        _LOGGER.debug(f"new state:{self}")
        self.publish_updates()

    def __repr__(self):
        return {
            "device_name": self.device_name,
            "thing_name": self.thing_name,
            "mac": self.mac,
            "firmware_version": self.firmware_version,
            "is_online": self.is_online,
            "is_on": self.is_on,
            "is_playing": self.is_playing,
            "volume": self.volume,
            "red": self.red,
            "green": self.green,
            "blue": self.blue,
            "brightness": self.brightness,
            "document_version": self.document_version,
            "charging_status": self.charging_status,
            "clock": self.clock,
            "flags": self.flags,
            "is_clock_on": self.is_clock_on,
            "is_clock_24h": self.is_clock_24h,
        }

    def __str__(self):
        return f"{self.__repr__()}"

    @property
    def is_on(self):
        return self.is_light_on or self.is_playing

    @property
    def is_light_on(self):
        return self.color_id != 9998 and self.color_id != 0

    @property
    def is_playing(self):
        return self.sound_id != 19998

    @property
    def is_clock_on(self):
        return self.flags is not None and self.flags & RIOT_FLAGS_CLOCK_ON

    @property
    def is_clock_24h(self):
        return self.flags is not None and self.flags & RIOT_FLAGS_CLOCK_24_HOUR

    def set_volume(self, percentage: int):
        _LOGGER.debug(f"Setting volume: {percentage}")
        self._update({"current": {"sound": {"v": convert_from_percentage(percentage)}}})

    def set_clock(self, brightness: int = 0):
        _LOGGER.debug(f"Setting clock on: {brightness}")
        self._update(
            {"clock": {"flags": self.flags | RIOT_FLAGS_CLOCK_ON, "i": convert_from_percentage(brightness)}}
        )

    def turn_clock_off(self):
        _LOGGER.debug("Turn off clock")
        self._update({"clock": {"flags": self.flags ^ RIOT_FLAGS_CLOCK_ON, "i": 655}})

    def turn_off(self):
        _LOGGER.debug("Turning off sound")
        self._update({"current": {"srId": 0, "step": 0, "playing": "none"}})

    def turn_light_off(self):
        _LOGGER.debug("Turning light off")
        # 9999 = custom color 9998 = turn off
        # if favorite is playing then light can be turned off without turning off sound
        if self.current_playing == "routine":
            self._update(
                {
                    "current": {
                        "color": {
                            "id": 9998,
                            "r": 0,
                            "g": 0,
                            "b": 0,
                            "w": 0,
                        }
                    }
                }
            )
        if self.current_playing == "remote":
            self._update(
                {
                    "current": {
                        "playing": "none",
                        "color": {
                            "id": 9998,
                            "r": 0,
                            "g": 0,
                            "b": 0,
                            "w": 0,
                        },
                    }
                }
            )

    def set_color(
        self, red: int, green: int, blue: int, white: int = 0, brightness: int = 0
    ):
        # 9999 = custom color 9998 = turn off
        new_color_id: int = 9999
        _LOGGER.debug(
            f"red: {red} green: {green} blue: {blue} brightness: {brightness} white: {white}"
        )
        # If there is no sound playing, and you want to turn on the light the playing value has to be set to remote
        if self.current_playing == "none":
            self._update(
                {
                    "current": {
                        "srId": 0,
                        "step": 0,
                        "playing": "remote",
                        "color": {
                            "id": new_color_id,
                            "r": convert_from_hex(red),
                            "g": convert_from_hex(green),
                            "b": convert_from_hex(blue),
                            "i": convert_from_percentage(brightness),
                            "w": convert_from_hex(white),
                        },
                    }
                }
            )
        self._update(
            {
                "current": {
                    "color": {
                        "id": new_color_id,
                        "r": convert_from_hex(red),
                        "g": convert_from_hex(green),
                        "b": convert_from_hex(blue),
                        "i": convert_from_percentage(brightness),
                        "w": convert_from_hex(white),
                    }
                }
            }
        )
