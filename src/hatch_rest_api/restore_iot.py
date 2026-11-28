"""Hatch Restore (1st gen) device."""

import logging
from typing import Any

from .const import RIOT_FLAGS_CLOCK_24_HOUR
from .iot_device import IotDevice
from .scheduled_routine import ScheduledRoutineAlarmMixin
from .util import convert_to_percentage, safely_get_json_value

_LOGGER = logging.getLogger(__name__)


class RestoreIot(ScheduledRoutineAlarmMixin, IotDevice):
    """Hatch Restore (1st gen) sunrise alarm, sound machine and light."""

    _scale_white = True

    audio_track: str | None = None

    charging_status: int | None = (
        None  # Expected values: 0= Not Charging, 3= Charging, plugged in, 5= Charging, on base
    )
    clock: int = 0

    def _update_device_state(self, state: dict[str, Any]) -> None:
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

    @property
    def is_clock_24h(self) -> bool:
        """Whether the clock displays 24-hour time."""
        return self.flags is not None and bool(self.flags & RIOT_FLAGS_CLOCK_24_HOUR)
