"""Hatch Rest 2nd gen (IoT) device."""

import contextlib
import logging
from typing import Any

from .const import NO_SOUND_ID, RIoTAudioTrack
from .iot_device import Clock24HourMixin, IotRestDevice
from .util import convert_from_hex, convert_from_percentage, safely_get_json_value

_LOGGER = logging.getLogger(__name__)


class RestIot(Clock24HourMixin, IotRestDevice):
    """Hatch Rest 2nd gen sound machine and night light."""

    audio_track: RIoTAudioTrack | None = None

    def _update_device_state(self, state: dict[str, Any]) -> None:
        super()._update_device_state(state)
        if safely_get_json_value(state, "current.sound.id", int) is not None:
            with contextlib.suppress(ValueError):
                self.audio_track = RIoTAudioTrack(self.sound_id)

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
