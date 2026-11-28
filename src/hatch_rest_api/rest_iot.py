"""Hatch Rest 2nd gen (IoT) device."""

import contextlib
import logging
from typing import Any

from .const import NO_SOUND_ID, RIOT_FLAGS_CLOCK_24_HOUR, RIoTAudioTrack
from .iot_device import IotSoundDevice
from .util import (
    convert_from_hex,
    convert_from_percentage,
    convert_to_percentage,
    safely_get_json_value,
)

_LOGGER = logging.getLogger(__name__)


class RestIot(IotSoundDevice):
    """Hatch Rest 2nd gen sound machine and night light."""

    audio_track: RIoTAudioTrack | None = None

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
        if safely_get_json_value(state, "current.sound.id", int) is not None:
            with contextlib.suppress(ValueError):
                self.audio_track = RIoTAudioTrack(self.sound_id)
        if safely_get_json_value(state, "clock.i") is not None:
            self.clock = convert_to_percentage(safely_get_json_value(state, "clock.i", int))

    def as_dict(self) -> dict[str, Any]:
        """Return the device state as a dictionary, for diagnostics and debugging."""
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
            "battery_level": self.battery_level,
            "is_playing": self.is_playing,
            "audio_track": self.audio_track,
            "sound_id": self.sound_id,
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
            "toddler_lock": self.toddler_lock,
            "toddler_lock_mode": self.toddler_lock_mode,
        }

    @property
    def is_clock_24h(self) -> bool:
        """Whether the clock displays 24-hour time."""
        return self.flags is not None and bool(self.flags & RIOT_FLAGS_CLOCK_24_HOUR)

    def set_toddler_lock(self, on: bool) -> None:
        """Turn the toddler lock on (mode ``always``) or off (mode ``never``).

        The API also supports a ``custom`` mode for a time range, which is not exposed here.
        """
        _LOGGER.debug("Setting Toddler On Lock: %s", on)
        mode = "always" if on else "never"
        self._update({"toddlerLock": {"turnOnMode": mode}})

    def set_audio_track(self, audio_track: RIoTAudioTrack) -> None:
        """Play ``audio_track``, or turn off for ``RIoTAudioTrack.NONE``."""
        _LOGGER.debug("Setting audio track: %s", audio_track)
        if audio_track == RIoTAudioTrack.NONE:
            self.turn_off()
            return

        sound_url_map = RIoTAudioTrack.sound_url_map()
        # update the map with any changes from the API
        sound_url_map.update(
            {
                sound_id: wav_url
                for sound in self.sounds
                if (sound_id := sound.get("id")) and (wav_url := sound.get("wavUrl"))
            }
        )
        _LOGGER.debug("Available Sounds: %s", sound_url_map)
        self._update(
            {
                "current": {
                    "playing": "remote",
                    "step": 1,
                    "sound": {
                        "id": audio_track.value,
                        "url": sound_url_map[audio_track.value],
                        "mute": False,
                        "until": "indefinite",
                    },
                }
            }
        )

    def set_sound_url(
        self,
        sound_url: str = "http://codeskulptor-demos.commondatastorage.googleapis.com/GalaxyInvaders/theme_01.mp3",
    ) -> None:
        """Appears to work with some but not all public wav and mp3 urls.

        i.e. http://codeskulptor-demos.commondatastorage.googleapis.com/GalaxyInvaders/theme_01.mp3
        """
        _LOGGER.debug("Setting sound URL: %s", sound_url)
        self._update(
            {
                "current": {
                    "playing": "remote",
                    "sound": {"mute": False, "url": sound_url},
                }
            }
        )

    def stop_sound(self) -> None:
        """Stop the sound only; a light that is on stays on.

        With no light on, this turns the device off.
        """
        _LOGGER.debug("Stopping sound")
        if not self.is_light_on:
            self.turn_off()
            return
        # Take manual control (a favorite would re-apply its own sound), keeping the light as it is.
        self._update(
            {
                "current": {
                    "srId": 0,
                    "step": 0,
                    "playing": "remote",
                    "sound": {"id": NO_SOUND_ID, "mute": False, "until": "indefinite"},
                    "color": {
                        "id": self.color_id,
                        "r": convert_from_hex(self.red),
                        "g": convert_from_hex(self.green),
                        "b": convert_from_hex(self.blue),
                        "i": convert_from_percentage(self.brightness),
                        "w": self.white,
                    },
                }
            }
        )
