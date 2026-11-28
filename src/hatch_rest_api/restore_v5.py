"""Hatch Restore 3 (V5) device."""

from datetime import time
import logging
from typing import Any

from .const import (
    CLOCK_TURN_OFF_MODE_ALWAYS,
    CLOCK_TURN_OFF_MODES,
    RIOT_FLAGS_CLOCK_IGNORE_TAP,
    RIOT_FLAGS_CLOCK_ON,
)
from .iot_device import Clock24HourMixin, IotSoundDevice
from .scheduled_routine import ScheduledRoutineAlarmMixin
from .util import safely_get_json_value

_LOGGER = logging.getLogger(__name__)


class RestoreV5(ScheduledRoutineAlarmMixin, Clock24HourMixin, IotSoundDevice):
    """Hatch Restore 3 sunrise alarm, sound machine and light."""

    _scale_white = True

    current_id: int = 0
    current_step: int = 0
    clock_nighttime: int | None = None
    clock_daytime: int | None = None
    clock_turn_off_mode: str | None = None
    clock_turn_off_at: str | None = None
    clock_turn_on_at: str | None = None
    clock_turn_dim_at: str | None = None
    clock_turn_bright_at: str | None = None

    def _update_device_state(self, state: dict[str, Any]) -> None:
        if safely_get_json_value(state, "current.srId") is not None:
            self.current_id = safely_get_json_value(state, "current.srId")
        if safely_get_json_value(state, "current.step") is not None:
            self.current_step = safely_get_json_value(state, "current.step")
        if safely_get_json_value(state, "clock.i") is not None:
            self.clock_nighttime, self.clock_daytime = unpack_dual_percentages(
                safely_get_json_value(state, "clock.i", int)
            )
        if safely_get_json_value(state, "clock.turnOffMode") is not None:
            self.clock_turn_off_mode = safely_get_json_value(state, "clock.turnOffMode")
        if safely_get_json_value(state, "clock.turnOffAt") is not None:
            self.clock_turn_off_at = safely_get_json_value(state, "clock.turnOffAt")
        if safely_get_json_value(state, "clock.turnOnAt") is not None:
            self.clock_turn_on_at = safely_get_json_value(state, "clock.turnOnAt")
        if safely_get_json_value(state, "clock.turnDimAt") is not None:
            self.clock_turn_dim_at = safely_get_json_value(state, "clock.turnDimAt")
        if safely_get_json_value(state, "clock.turnBrightAt") is not None:
            self.clock_turn_bright_at = safely_get_json_value(state, "clock.turnBrightAt")

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
            "clock_turn_off_mode": self.clock_turn_off_mode,
            "clock_turn_off_at": self.clock_turn_off_at,
            "clock_turn_on_at": self.clock_turn_on_at,
            "clock_turn_dim_at": self.clock_turn_dim_at,
            "clock_turn_bright_at": self.clock_turn_bright_at,
            "is_clock_on": self.is_clock_on,
            "is_clock_24h": self.is_clock_24h,
        }

    @property
    def clock(self) -> int:
        """Daytime clock brightness as a 0-100 percentage."""
        return self.clock_daytime or 0

    def set_clock(
        self,
        daytime_brightness: int | None = None,
        nighttime_brightness: int | None = None,
    ) -> None:
        """Turn the clock display on.

        Args:
            daytime_brightness: Daytime brightness percentage; defaults to the current value.
            nighttime_brightness: Nighttime brightness percentage; defaults to the current value.
        """
        if daytime_brightness is None:
            daytime_brightness = self.clock_daytime or 0
        if nighttime_brightness is None:
            nighttime_brightness = self.clock_nighttime or 0
        _LOGGER.debug(
            "Setting clock on: daytime=%s nighttime=%s", daytime_brightness, nighttime_brightness
        )
        self._update(
            {
                "clock": {
                    "flags": self.flags | RIOT_FLAGS_CLOCK_ON,
                    "i": pack_dual_percentages(nighttime_brightness, daytime_brightness),
                }
            }
        )

    def turn_clock_off(self) -> None:
        """Turn the clock display off, keeping its brightness settings."""
        _LOGGER.debug("Turn off clock")
        clock = {"flags": self.flags & ~RIOT_FLAGS_CLOCK_ON}
        # Only re-send the packed brightness when both channels are known, so an
        # off call before the device has reported clock.i doesn't zero it out.
        if self.clock_nighttime is not None and self.clock_daytime is not None:
            clock["i"] = pack_dual_percentages(self.clock_nighttime, self.clock_daytime)
        self._update({"clock": clock})

    def set_clock_turn_off_mode(self, mode: str) -> None:
        """Set when the clock display turns off.

        ``always`` also clears the clock-on flag; ``never`` and ``custom`` set it.

        Args:
            mode: One of ``CLOCK_TURN_OFF_MODES``: ``never`` (always on), ``custom``
                (off at night, per the turn off/on times) or ``always`` (always off).

        Raises:
            ValueError: If ``mode`` is not a known turn-off mode.
        """
        if mode not in CLOCK_TURN_OFF_MODES:
            msg = f"Unknown clock turn off mode: {mode!r}"
            raise ValueError(msg)
        _LOGGER.debug("Setting clock turn off mode: %s", mode)
        if mode == CLOCK_TURN_OFF_MODE_ALWAYS:
            flags = self.flags & ~RIOT_FLAGS_CLOCK_ON
        else:
            flags = self.flags | RIOT_FLAGS_CLOCK_ON
        self._update({"clock": {"flags": flags, "turnOffMode": mode}})

    def set_clock_turn_on_at(self, value: time) -> None:
        """Set when the clock display turns on (and brightens) each day.

        Writes both ``turnOnAt`` and ``turnBrightAt``, matching the single start
        time shown in the Hatch app.

        Args:
            value: Local time of day the clock turns on.
        """
        self._set_clock_schedule_time(("turnOnAt", "turnBrightAt"), value)

    def set_clock_turn_off_at(self, value: time) -> None:
        """Set when the clock display turns off (and dims) each day.

        Writes both ``turnOffAt`` and ``turnDimAt``, matching the single end
        time shown in the Hatch app.

        Args:
            value: Local time of day the clock turns off.
        """
        self._set_clock_schedule_time(("turnOffAt", "turnDimAt"), value)

    def _set_clock_schedule_time(self, shadow_keys: tuple[str, ...], value: time) -> None:
        """Write one time of day to several clock schedule shadow keys.

        Args:
            shadow_keys: The ``clock`` shadow keys to write.
            value: The time of day, sent as ``HH:MM:SS``.
        """
        time_str = value.strftime("%H:%M:%S")
        _LOGGER.debug("Setting clock %s: %s", "/".join(shadow_keys), time_str)
        self._update({"clock": dict.fromkeys(shadow_keys, time_str)})

    @property
    def is_clock_tap_on(self) -> bool | None:
        """Whether tapping the device shows the clock, or None before flags are known."""
        if self.flags is None:
            return None
        return not (self.flags & RIOT_FLAGS_CLOCK_IGNORE_TAP)

    def clock_tap_on(self) -> None:
        """Enable tap-to-show: a tap on the device shows the clock."""
        _LOGGER.debug("Turn on clock tap to show")
        self._update({"clock": {"flags": self.flags & ~RIOT_FLAGS_CLOCK_IGNORE_TAP}})

    def clock_tap_off(self) -> None:
        """Disable tap-to-show: the device ignores taps for showing the clock."""
        _LOGGER.debug("Turn off clock tap to show")
        self._update({"clock": {"flags": self.flags | RIOT_FLAGS_CLOCK_IGNORE_TAP}})


def unpack_dual_percentages(packed_value: int) -> tuple[int, int]:
    """Unpack two percentages from a 32-bit integer."""
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
    """Pack two percentages into a 32-bit integer."""
    # Convert percentages to 16-bit integers (0-65535 range)
    a_16bit = round(a_percentage / 100.0 * 65535)
    b_16bit = round(b_percentage / 100.0 * 65535)

    # Pack two 16-bit integers into one 32-bit integer
    # A goes in upper 16 bits, B in lower 16 bits
    a_16bit = a_16bit & 0xFFFF
    b_16bit = b_16bit & 0xFFFF

    # Shift the upper value left by 16 bits and OR with the lower value
    return (a_16bit << 16) | b_16bit
