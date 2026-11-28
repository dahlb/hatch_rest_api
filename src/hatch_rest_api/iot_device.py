"""Shared base classes for the IoT-shadow devices with a light, sound and clock.

RestIot, RestBaby, RestoreIot and RestoreV5 (and RestoreV4) report and accept the
same ``current`` / ``clock`` shadow layout for their light, sound and clock. The
code they share lives here; each device class keeps what only it has.

Only members every subclass already had belong on ``IotDevice``: Home Assistant
integrations detect features with ``isinstance`` and ``hasattr``, so a base class
must not give a device an attribute or method it didn't have.
"""

import logging
from typing import TYPE_CHECKING, Any

from .const import (
    CUSTOM_COLOR_ID,
    NO_COLOR_ID,
    NO_SOUND_ID,
    RIOT_FLAGS_CLOCK_24_HOUR,
    RIOT_FLAGS_CLOCK_ON,
)
from .shadow_client_subscriber import ShadowClientSubscriberMixin
from .types import SimpleSoundContent, SoundContent
from .util import (
    convert_from_hex,
    convert_from_percentage,
    convert_to_hex,
    convert_to_percentage,
    safely_get_json_value,
)

_LOGGER = logging.getLogger(__name__)


class IotDevice(ShadowClientSubscriberMixin):
    """Light, volume, clock and favorites shared by the IoT-shadow devices.

    Subclasses read their own extra shadow fields in ``_update_device_state``.
    """

    # Whether the device reports and takes the white channel on the 16-bit scale
    # (the Restores) rather than as a raw value (the Rests).
    _scale_white: bool = False

    firmware_version: str | None = None
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
            white = safely_get_json_value(state, "current.color.w", int)
            self.white = convert_to_hex(white) if self._scale_white else white
        if safely_get_json_value(state, "current.color.i") is not None:
            self.brightness = convert_to_percentage(
                safely_get_json_value(state, "current.color.i", int)
            )
        if safely_get_json_value(state, "clock.flags") is not None:
            self.flags = safely_get_json_value(state, "clock.flags", int)
        self._update_device_state(state)

        _LOGGER.debug("new state:%s", self)
        self.publish_updates()

    def _update_device_state(self, state: dict[str, Any]) -> None:
        """Read the shadow fields only this device class has."""

    # ---- read-only views ----------------------------------------------------

    @property
    def is_on(self) -> bool:
        """Whether the light or a sound is on."""
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
        return bool(self.flags & RIOT_FLAGS_CLOCK_ON)

    def favorite_names(self, active_only: bool = False) -> list[str]:
        """Return favorites as ``name-id`` strings.

        Args:
            active_only: Only return favorites marked active in the Hatch app.

        Returns:
            One ``name-id`` string per favorite.
        """
        return [
            f"{favorite['name']}-{favorite['id']}"
            for favorite in self.favorites
            if not active_only or favorite.get("active")
        ]

    # ---- commands -------------------------------------------------------------

    def set_volume(self, percentage: int) -> None:
        """Set the volume as a 0-100 percentage."""
        _LOGGER.debug("Setting volume: %s", percentage)
        self._update({"current": {"sound": {"v": convert_from_percentage(percentage)}}})

    def set_clock(self, brightness: int = 0) -> None:
        """Turn the clock display on at ``brightness`` percent."""
        _LOGGER.debug("Setting clock on: %s", brightness)
        self._update(
            {
                "clock": {
                    "flags": (self.flags or 0) | RIOT_FLAGS_CLOCK_ON,
                    "i": convert_from_percentage(brightness),
                }
            }
        )

    def turn_clock_off(self) -> None:
        """Turn the clock display off."""
        _LOGGER.debug("Turn off clock")
        self._update({"clock": {"flags": (self.flags or 0) ^ RIOT_FLAGS_CLOCK_ON, "i": 655}})

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
        """Turn off the light, leaving any playing sound on."""
        _LOGGER.debug("Turning light off")
        color_off = {
            "id": NO_COLOR_ID,
            "r": 0,
            "g": 0,
            "b": 0,
            "w": 0,
        }
        # Only the light: a sound that is playing keeps playing (favorites and remote alike).
        if self.current_playing == "routine" or (
            self.current_playing == "remote" and self.is_playing
        ):
            self._update({"current": {"color": color_off}})
        elif self.current_playing == "remote":
            self._update({"current": {"playing": "none", "color": color_off}})

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
        _LOGGER.debug(
            "red: %s green: %s blue: %s brightness: %s white: %s",
            red,
            green,
            blue,
            brightness,
            white,
        )
        color = {
            "id": CUSTOM_COLOR_ID,
            "r": convert_from_hex(red),
            "g": convert_from_hex(green),
            "b": convert_from_hex(blue),
            "i": convert_from_percentage(brightness),
            "w": convert_from_hex(white) if self._scale_white else white,
        }
        # With no sound playing, turning on the light requires setting playing to remote.
        if self.current_playing == "none":
            self._update({"current": {"srId": 0, "step": 0, "playing": "remote", "color": color}})
        else:
            self._update({"current": {"color": color}})


class IotSoundDevice(IotDevice):
    """An ``IotDevice`` that can play a sound from its sound content."""

    def _sound_command_extras(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return extra ``current`` and ``sound`` fields a device sends with a sound."""
        return {}, {}

    def set_sound(
        self,
        sound_or_id_or_title: SoundContent | SimpleSoundContent | str | int | None,
        duration: int = 0,
        until: str = "indefinite",
    ) -> None:
        """Set a sound by passing SoundContent item from self.sounds, id, or title."""
        if sound_or_id_or_title is None or sound_or_id_or_title in (NO_SOUND_ID, "none"):
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
            _LOGGER.error("Sound not found: %s", sound_or_id_or_title)
            return

        _LOGGER.debug("Setting sound: %s", sound.get("title") or sound["id"])
        current_extras, sound_extras = self._sound_command_extras()
        self._update(
            {
                "current": {
                    "playing": "remote",
                    **current_extras,
                    "sound": {
                        "id": sound["id"],
                        "mute": False,
                        "url": sound.get("wavUrl") or sound.get("mp3Url"),
                        "duration": duration,
                        "until": until,
                        **sound_extras,
                    },
                }
            }
        )


class IotRestDevice(IotSoundDevice):
    """The Rest family's (RestIot and RestBaby) battery, toddler lock and favorite progress.

    Subclasses that extend ``_update_device_state`` call ``super()`` first.
    """

    current_id: int = 0
    current_step: int = 0
    battery_level: int | None = None
    charging_status: int | None = (
        None  # Expected values: 0= Not Charging, 3= Charging, plugged in, 5= Charging, on base
    )
    clock: int | None = None
    toddler_lock: bool = False
    toddler_lock_mode: str | None = None

    def _update_device_state(self, state: dict[str, Any]) -> None:
        if safely_get_json_value(state, "deviceInfo.b") is not None:
            self.battery_level = safely_get_json_value(state, "deviceInfo.b", int)
        if safely_get_json_value(state, "deviceInfo.powerStatus") is not None:
            self.charging_status = safely_get_json_value(state, "deviceInfo.powerStatus", int)
        if safely_get_json_value(state, "toddlerLockOn") is not None:
            self.toddler_lock = safely_get_json_value(state, "toddlerLockOn", bool)
        if safely_get_json_value(state, "toddlerLock.turnOnMode") is not None:
            self.toddler_lock_mode = safely_get_json_value(state, "toddlerLock.turnOnMode", str)
        if safely_get_json_value(state, "current.srId") is not None:
            self.current_id = safely_get_json_value(state, "current.srId")
        if safely_get_json_value(state, "current.step") is not None:
            self.current_step = safely_get_json_value(state, "current.step")
        if safely_get_json_value(state, "clock.i") is not None:
            self.clock = convert_to_percentage(safely_get_json_value(state, "clock.i", int))

    def _sound_url_command_extras(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return extra ``current`` and ``sound`` fields a device sends with a sound URL."""
        return {}, {}

    def set_toddler_lock(self, on: bool) -> None:
        """Turn the toddler lock on (mode ``always``) or off (mode ``never``).

        The API also supports a ``custom`` mode for a time range, which is not exposed here.
        """
        _LOGGER.debug("Setting toddler lock: %s", on)
        mode = "always" if on else "never"
        self._update({"toddlerLock": {"turnOnMode": mode}})

    def set_sound_url(
        self,
        sound_url: str = "http://codeskulptor-demos.commondatastorage.googleapis.com/GalaxyInvaders/theme_01.mp3",
    ) -> None:
        """Appears to work with some but not all public wav and mp3 urls.

        i.e. http://codeskulptor-demos.commondatastorage.googleapis.com/GalaxyInvaders/theme_01.mp3
        """
        _LOGGER.debug("Setting sound URL: %s", sound_url)
        current_extras, sound_extras = self._sound_url_command_extras()
        self._update(
            {
                "current": {
                    "playing": "remote",
                    **current_extras,
                    "sound": {"mute": False, "url": sound_url, **sound_extras},
                }
            }
        )


class Clock24HourMixin:
    """``is_clock_24h`` for the devices that report a 24-hour clock flag.

    RestIot, RestoreIot and RestoreV5 have it; RestBaby doesn't. List it before
    the ``IotDevice`` base.
    """

    if TYPE_CHECKING:
        flags: int

    @property
    def is_clock_24h(self) -> bool:
        """Whether the clock displays 24-hour time."""
        return bool(self.flags & RIOT_FLAGS_CLOCK_24_HOUR)
