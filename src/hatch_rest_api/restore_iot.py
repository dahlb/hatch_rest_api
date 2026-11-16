"""Hatch Restore (1st gen) device."""

import logging
from typing import Any

from .const import (
    CUSTOM_COLOR_ID,
    NO_COLOR_ID,
    NO_SOUND_ID,
    RIOT_FLAGS_CLOCK_24_HOUR,
    RIOT_FLAGS_CLOCK_ON,
)
from .scheduled_routine import ScheduledRoutineAlarmMixin
from .shadow_client_subscriber import ShadowClientSubscriberMixin
from .util import (
    convert_from_hex,
    convert_from_percentage,
    convert_to_hex,
    convert_to_percentage,
    safely_get_json_value,
)

_LOGGER = logging.getLogger(__name__)


class RestoreIot(ScheduledRoutineAlarmMixin, ShadowClientSubscriberMixin):
    """Hatch Restore (1st gen) sunrise alarm, sound machine and light."""

    audio_track: str = None
    firmware_version: str = None
    volume: int = 0

    is_online: bool = False
    current_playing: str = "none"

    color_id: int = NO_COLOR_ID
    sound_id: int = NO_SOUND_ID
    red: int = 0
    green: int = 0
    blue: int = 0
    white: int = 0
    brightness: int = 0
    charging_status: int = (
        None  # Expected values: 0= Not Charging, 3= Charging, plugged in, 5= Charging, on base
    )
    clock: int = 0
    flags: int = 0

    def _update_local_state(self, state: dict[str, Any]) -> None:
        _LOGGER.debug("update local state: %s, %s", self.device_name, state)
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
            self.red = convert_to_hex(safely_get_json_value(state, "current.color.r", int))
        if safely_get_json_value(state, "current.color.g") is not None:
            self.green = convert_to_hex(safely_get_json_value(state, "current.color.g", int))
        if safely_get_json_value(state, "current.color.b") is not None:
            self.blue = convert_to_hex(safely_get_json_value(state, "current.color.b", int))
        if safely_get_json_value(state, "current.color.w") is not None:
            self.white = convert_to_hex(safely_get_json_value(state, "current.color.w", int))
        if safely_get_json_value(state, "current.color.i") is not None:
            self.brightness = convert_to_percentage(
                safely_get_json_value(state, "current.color.i", int)
            )
        if safely_get_json_value(state, "clock.i") is not None:
            self.clock = convert_to_percentage(safely_get_json_value(state, "clock.i", int))
        if safely_get_json_value(state, "clock.flags") is not None:
            self.flags = safely_get_json_value(state, "clock.flags", int)

        _LOGGER.debug("new state:%s", self)
        self.publish_updates()

    def __repr__(self) -> str:
        """Return the device state as a dictionary for debugging."""
        return {
            "device_name": self.device_name,
            "thing_name": self.thing_name,
            "mac": self.mac,
            "firmware_version": self.firmware_version,
            "is_online": self.is_online,
            "is_on": self.is_on,
            "is_playing": self.is_playing,
            "audio_track": self.audio_track,
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

    def __str__(self) -> str:
        """Return the device state as a string."""
        return f"{self.__repr__()}"

    @property
    def is_on(self) -> bool:
        """Whether the light is on or a sound is playing."""
        return self.is_light_on or self.is_playing

    @property
    def is_light_on(self) -> bool:
        """Whether the light is on."""
        return self.color_id not in (NO_COLOR_ID, 0)

    @property
    def is_playing(self) -> bool:
        """Whether a sound is playing."""
        return self.sound_id != NO_SOUND_ID

    @property
    def is_clock_on(self) -> bool:
        """Whether the clock display is on."""
        return self.flags is not None and bool(self.flags & RIOT_FLAGS_CLOCK_ON)

    @property
    def is_clock_24h(self) -> bool:
        """Whether the clock displays 24-hour time."""
        return self.flags is not None and bool(self.flags & RIOT_FLAGS_CLOCK_24_HOUR)

    def set_volume(self, percentage: int) -> None:
        """Set the volume as a 0-100 percentage."""
        _LOGGER.debug("Setting volume: %s", percentage)
        self._update({"current": {"sound": {"v": convert_from_percentage(percentage)}}})

    def favorite_names(self, active_only: bool = True) -> list[str]:
        """Return favorites as ``name-id`` strings.

        Args:
            active_only: Currently has no effect; every favorite is returned.

        Returns:
            One ``name-id`` string per favorite.
        """
        names = []
        for favorite in self.favorites:
            if active_only and favorite["active"]:
                names.append(f"{favorite['name']}-{favorite['id']}")
            else:
                names.append(f"{favorite['name']}-{favorite['id']}")
        return names

    def set_clock(self, brightness: int = 0) -> None:
        """Turn the clock display on at ``brightness`` percent."""
        _LOGGER.debug("Setting clock on: %s", brightness)
        self._update(
            {
                "clock": {
                    "flags": self.flags | RIOT_FLAGS_CLOCK_ON,
                    "i": convert_from_percentage(brightness),
                }
            }
        )

    def turn_clock_off(self) -> None:
        """Turn the clock display off."""
        _LOGGER.debug("Turn off clock")
        self._update({"clock": {"flags": self.flags ^ RIOT_FLAGS_CLOCK_ON, "i": 655}})

    def set_favorite(self, favorite_name_id: str) -> None:
        """Start a favorite routine.

        Args:
            favorite_name_id: ``name-id`` string from ``favorite_names``; names alone
                are not unique.
        """
        _LOGGER.debug("Setting favorite: %s", favorite_name_id)
        fav_id = int(favorite_name_id.rsplit("-", 1)[1])
        self._update({"current": {"srId": fav_id, "step": 1, "playing": "routine"}})

    def turn_off(self) -> None:
        """Turn off sound and light by stopping the current routine."""
        _LOGGER.debug("Turning off sound")
        self._update({"current": {"srId": 0, "step": 0, "playing": "none"}})

    def turn_light_off(self) -> None:
        """Turn off the light; a playing favorite keeps its sound."""
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
        """Set the light color.

        Args:
            red: Red channel, 0-255.
            green: Green channel, 0-255.
            blue: Blue channel, 0-255.
            white: White channel value.
            brightness: Brightness as a 0-100 percentage.
        """
        new_color_id = CUSTOM_COLOR_ID
        _LOGGER.debug(
            "red: %s green: %s blue: %s brightness: %s white: %s",
            red,
            green,
            blue,
            brightness,
            white,
        )
        # With no sound playing, turning on the light requires setting playing to remote.
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
