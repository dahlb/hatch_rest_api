import logging
from typing import cast

from .util import (
    convert_to_percentage,
    safely_get_json_value,
    convert_from_percentage,
    convert_from_hex,
    convert_to_hex,
)
from .const import (
    RIOT_FLAGS_CLOCK_ON,
    RIOT_FLAGS_CLOCK_24_HOUR,
    NO_SOUND_ID,
    NO_COLOR_ID,
    CUSTOM_COLOR_ID,
)
from .shadow_client_subscriber import ShadowClientSubscriberMixin
from .types import IotSoundUntil, JsonType, SimpleSoundContent, SoundContent

_LOGGER = logging.getLogger(__name__)


class RestoreV5(ShadowClientSubscriberMixin):
    firmware_version: str | None = None
    volume: int = 0

    is_online: bool = False
    current_playing: str = "none"
    current_id: int = 0
    current_step: int = 0
    color_id: int = NO_COLOR_ID
    sound_id: int = NO_SOUND_ID
    red: int = 0
    green: int = 0
    blue: int = 0
    white: int = 0
    brightness: int = 0
    clock_nighttime: int = 0
    clock_daytime: int = 0
    flags: int = 0

    def _update_local_state(self, state: dict[str, JsonType]) -> None:
        _LOGGER.debug(f"update local state: {self.device_name}, {state}")
        if safely_get_json_value(state, "deviceInfo.f") is not None:
            self.firmware_version = safely_get_json_value(state, "deviceInfo.f")
        if safely_get_json_value(state, "current.playing") is not None:
            self.current_playing = safely_get_json_value(state, "current.playing")
        if safely_get_json_value(state, "current.srId") is not None:
            self.current_id = safely_get_json_value(state, "current.srId")
        if safely_get_json_value(state, "current.step") is not None:
            self.current_step = safely_get_json_value(state, "current.step")
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
            self.clock_nighttime, self.clock_daytime = unpack_dual_percentages(safely_get_json_value(state, "clock.i", int))
        if safely_get_json_value(state, "clock.flags") is not None:
            self.flags = safely_get_json_value(state, "clock.flags", int)

        _LOGGER.debug(f"new state:{self}")
        self.publish_updates()

    def __repr__(self) -> dict[str, JsonType]:
        return {
            "device_name": self.device_name,
            "thing_name": self.thing_name,
            "mac": self.mac,
            "firmware_version": self.firmware_version,
            "is_online": self.is_online,
            "current_playing": self.current_playing,
            "current_id": self.current_id,
            "current_step": self.current_step,
            "is_on": self.is_on,
            "is_playing": self.is_playing,
            "sound_id": self.sound_id,
            "volume": self.volume,
            "red": self.red,
            "green": self.green,
            "blue": self.blue,
            "brightness": self.brightness,
            "document_version": self.document_version,
            "clock_nighttime": self.clock_nighttime,
            "clock_daytime": self.clock_daytime,
            "flags": self.flags,
            "is_clock_on": self.is_clock_on,
            "is_clock_24h": self.is_clock_24h,
        }

    def __str__(self) -> str:
        return f"{self.__repr__()}"

    @property
    def is_on(self) -> bool:
        return self.is_light_on or self.is_playing

    @property
    def is_light_on(self) -> bool:
        return self.color_id != NO_COLOR_ID and self.color_id != 0

    @property
    def is_playing(self) -> bool:
        return self.sound_id != NO_SOUND_ID

    @property
    def is_clock_on(self) -> bool:
        return self.flags is not None and self.flags & RIOT_FLAGS_CLOCK_ON

    @property
    def is_clock_24h(self) -> bool:
        return self.flags is not None and self.flags & RIOT_FLAGS_CLOCK_24_HOUR

    @property
    def clock(self) -> int:
        return self.clock_daytime

    def set_volume(self, percentage: float) -> None:
        _LOGGER.debug(f"Setting volume: {percentage}")
        self._update({"current": {"sound": {"v": convert_from_percentage(percentage)}}})

    def favorite_names(self, active_only: bool = True) -> list[str]:
        names = []
        for favorite in self.favorites:
            if active_only and favorite["active"]:
                names.append(f"{favorite['name']}-{favorite['id']}")
            else:
                names.append(f"{favorite['name']}-{favorite['id']}")
        return names

    def set_clock(self, daytime_brightness: int | None = None, nighttime_brightness: int | None = None) -> None:
        if daytime_brightness is None:
            daytime_brightness = self.clock_daytime
        if nighttime_brightness is None:
            nighttime_brightness = self.clock_nighttime
        _LOGGER.debug(f"Setting clock on: daytime={daytime_brightness} nighttime={nighttime_brightness}")
        self._update(
            {"clock": {"flags": self.flags | RIOT_FLAGS_CLOCK_ON, "i": pack_dual_percentages(nighttime_brightness, daytime_brightness)}}
        )

    def turn_clock_off(self) -> None:
        _LOGGER.debug("Turn off clock")
        self._update({"clock": {"flags": self.flags ^ RIOT_FLAGS_CLOCK_ON, "i": 655}})

    # favorite_name_id is expected to be a string of name-id since name alone isn't unique
    def set_favorite(self, favorite_name_id: str) -> None:
        _LOGGER.debug(f"Setting favorite: {favorite_name_id}")
        fav_id = int(favorite_name_id.rsplit("-", 1)[1])
        self._update({"current": {"srId": fav_id, "step": 1, "playing": "routine"}})

    def set_sound(
        self,
        sound_or_id_or_title: SoundContent | SimpleSoundContent | str | int | None,
        duration: int = 0,
        until: IotSoundUntil = "indefinite",
    ) -> None:
        """Set a sound by passing SoundContent item from self.sounds, id, or title."""
        if sound_or_id_or_title is None or sound_or_id_or_title == NO_SOUND_ID or sound_or_id_or_title == "none":
            self.turn_off()
            return

        if isinstance(sound_or_id_or_title, int):
            sound = self.sounds_by_id.get(sound_or_id_or_title)
        elif isinstance(sound_or_id_or_title, str):
            sound = self.sounds_by_name.get(sound_or_id_or_title)
        else:
            # Assume it's a SoundContent or SimpleSoundContent object
            sound = sound_or_id_or_title

        if (
            not sound
            or not isinstance(sound, dict)
            or not sound.get("id")
            or (not sound.get("wavUrl") and not sound.get("mp3Url"))
        ):
            _LOGGER.error(f"Sound not found: {sound_or_id_or_title}")
            return

        _LOGGER.debug(f"Setting sound: {sound.get('title') or sound['id']}")
        self._update(
            {
                "current": {
                    "playing": "remote",
                    "sound": {
                        "id": sound["id"],
                        "mute": False,
                        "url": sound.get("wavUrl") or cast(SoundContent, sound).get("mp3Url"),
                        "duration": duration,
                        "until": until,
                    },
                }
            }
        )

    def turn_off(self) -> None:
        _LOGGER.debug("Turning off sound")
        self._update({"current": {"srId": 0, "step": 0, "playing": "none"}})

    def turn_light_off(self) -> None:
        _LOGGER.debug("Turning light off")
        # if favorite is playing then light can be turned off without turning off sound
        if self.current_playing == "routine":
            self._update(
                {
                    "current": {
                        "color": {
                            "id": NO_COLOR_ID,
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
                            "id": NO_COLOR_ID,
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
    ) -> None:
        new_color_id = CUSTOM_COLOR_ID
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
        else:
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

def unpack_dual_percentages(packed_value: int) -> tuple[int, int]:
    """
    Unpack two percentages from a 32-bit integer.
    """
    # Extract upper 16 bits (a)
    first_16bit = (packed_value >> 16) & 0xFFFF

    # Extract lower 16 bits (b)
    second_16bit = packed_value & 0xFFFF

    # Convert back to percentages (0.0 to 1.0 range)
    first_percentage = first_16bit / 65535.0
    second_percentage = second_16bit / 65535.0

    # Convert to 0-100 range and round to the nearest integer
    return round(first_percentage * 100), round(second_percentage * 100)


def pack_dual_percentages(a_percentage: int, b_percentage: int) -> int:
    """
    Pack two percentages into a 32-bit integer.
    """
    # Convert percentages to 16-bit integers (0-65535 range)
    a_16bit = round(a_percentage / 100.0 * 65535)
    b_16bit = round(b_percentage / 100.0 * 65535)

    # Pack two 16-bit integers into one 32-bit integer
    # A goes in upper 16 bits, B in lower 16 bits
    a_16bit = a_16bit & 0xFFFF
    b_16bit = b_16bit & 0xFFFF

    # Shift the upper value left by 16 bits and OR with the lower value
    return (a_16bit << 16) | b_16bit
