import logging

from .util import (
    convert_to_percentage,
    safely_get_json_value,
    convert_from_percentage,
    convert_from_hex,
    convert_to_hex,
)
from .shadow_client_subscriber import ShadowClientSubscriberMixin

_LOGGER = logging.getLogger(__name__)


class RestIot(ShadowClientSubscriberMixin):
    audio_track: str = None
    firmware_version: str = None
    volume: int = 0

    is_online: bool = False
    current_playing: str = "none"

    battery_level: int = None
    color_id: int = 9998
    sound_id: int = 19998
    red: int = 0
    green: int = 0
    blue: int = 0
    white: int = 0
    brightness: int = 0

    # Used to save the last light state so turning on the light will have a state to go
    # to when no color data is provided.
    # Defaults to 50% everything
    last_light_on_colors = {
        "r": convert_to_hex(32768),
        "g": convert_to_hex(32768),
        "b": convert_to_hex(32768),
        "w": 0,
        "i": convert_to_percentage(32768),
    }

    def _update_local_state(self, state):
        _LOGGER.debug(f"update local state: {self.device_name}, {state}")
        if safely_get_json_value(state, "deviceInfo.f") is not None:
            self.firmware_version = safely_get_json_value(state, "deviceInfo.f")
        if safely_get_json_value(state, "deviceInfo.b") is not None:
            self.battery_level = safely_get_json_value(state, "deviceInfo.b", int)
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
        if safely_get_json_value(state, "current.color.w") is not None:
            self.white = safely_get_json_value(state, "current.color.w", int)
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
        if safely_get_json_value(state, "current.color.i") is not None:
            self.brightness = convert_to_percentage(
                safely_get_json_value(state, "current.color.i", int)
            )
        # 9998 == off so only update the previous light state when it is something other than off
        if self.color_id != 9998:
            self._update_last_light_on_color()
        _LOGGER.debug(f"new state:{self}")
        self.publish_updates()

    def _update_last_light_on_color(self):
        self.last_light_on_colors["r"] = self.red
        self.last_light_on_colors["g"] = self.green
        self.last_light_on_colors["b"] = self.blue
        self.last_light_on_colors["w"] = self.white
        self.last_light_on_colors["i"] = self.brightness

    def __repr__(self):
        return {
            "device_name": self.device_name,
            "thing_name": self.thing_name,
            "mac": self.mac,
            "firmware_version": self.firmware_version,
            "is_online": self.is_online,
            "is_on": self.is_on,
            "battery_level": self.battery_level,
            "is_playing": self.is_playing,
            "volume": self.volume,
            "red": self.red,
            "green": self.green,
            "blue": self.blue,
            "brightness": self.brightness,
            "document_version": self.document_version,
        }

    def __str__(self):
        return f"{self.__repr__()}"

    @property
    def is_on(self):
        return self.is_light_on or self.is_playing

    @property
    def is_light_on(self):
        return self.color_id != 9998

    @property
    def is_playing(self):
        return self.sound_id != 19998

    def favorite_names(self, active_only: bool = True):
        names = []
        for favorite in self.favorites:
            if active_only and favorite["active"]:
                names.append(f"{favorite['name']}-{favorite['id']}")
            else:
                names.append(f"{favorite['name']}-{favorite['id']}")
        return names

    def set_volume(self, percentage: int):
        _LOGGER.debug(f"Setting volume: {percentage}")
        self._update({"current": {"sound": {"v": convert_from_percentage(percentage)}}})

    # favorite_name_id is expected to be a string of name-id since name alone isn't unique
    def set_favorite(self, favorite_name_id: str):
        _LOGGER.debug(f"Setting favorite: {favorite_name_id}")
        fav_id = int(favorite_name_id.split("-")[1])
        self._update({"current": {"srId": fav_id, "step": 1, "playing": "routine"}})

    def turn_off(self):
        _LOGGER.debug("Turning off sound")
        self._update({"current": {"srId": 0, "step": 0, "playing": "none"}})

    def set_on(self, on: bool):
        # Set the color to the stored defaults if turning on
        _LOGGER.debug(f"Setting on: {on}")
        self.set_color(0, 0, 0, 0, 0, on)

    def set_color(
        self,
        red: int,
        green: int,
        blue: int,
        white: int = 0,
        brightness: int = 0,
        on: bool = True,
    ):
        # 9999 = custom color 9998 = turn off
        new_color_id: int = 9999
        _LOGGER.debug(
            f"red: {red} green: {green} blue: {blue} brightness: {brightness} white: {white} on: {on}"
        )
        if on:
            if red == 0 and green == 0 and blue == 0 and white == 0:
                # We need to default turn on, we can use the last light color we have saved
                red = self.last_light_on_colors["r"]
                green = self.last_light_on_colors["g"]
                blue = self.last_light_on_colors["b"]
                white = self.last_light_on_colors["w"]
            if brightness == 0:
                brightness = self.last_light_on_colors["i"]
        else:
            new_color_id = 9998
        # If there is no sound playing, and you want to turn on the light the playing value has to be set to remote
        if self.current_playing == "none" and new_color_id == 9999:
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
                            "w": white,
                        }
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
                        "w": white,
                    }
                }
            }
        )
