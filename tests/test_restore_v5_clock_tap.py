"""Tests for RestoreV5 clock tap-to-show helpers."""

from typing import Any

from hatch_rest_api.const import RIOT_FLAGS_CLOCK_IGNORE_TAP, RIOT_FLAGS_CLOCK_ON
from hatch_rest_api.restore_v5 import RestoreV5


class _RecordingRestoreV5(RestoreV5):
    """RestoreV5 that records desired-state updates instead of publishing them."""

    def __init__(self, flags: int | None) -> None:
        self.flags = flags
        self.updates: list[dict[str, Any]] = []

    def _update(self, desired_state: dict[str, Any]) -> None:
        self.updates.append(desired_state)


def test_clock_tap_on_clears_ignore_tap_flag() -> None:
    """clock_tap_on clears only the ignore-tap bit."""
    device = _RecordingRestoreV5(RIOT_FLAGS_CLOCK_ON | RIOT_FLAGS_CLOCK_IGNORE_TAP)
    device.clock_tap_on()
    assert device.updates == [{"clock": {"flags": RIOT_FLAGS_CLOCK_ON}}]


def test_clock_tap_off_sets_ignore_tap_flag() -> None:
    """clock_tap_off sets only the ignore-tap bit."""
    device = _RecordingRestoreV5(RIOT_FLAGS_CLOCK_ON)
    device.clock_tap_off()
    expected = RIOT_FLAGS_CLOCK_ON | RIOT_FLAGS_CLOCK_IGNORE_TAP
    assert device.updates == [{"clock": {"flags": expected}}]


def test_is_clock_tap_on() -> None:
    """is_clock_tap_on reflects the inverse of the ignore-tap bit."""
    assert _RecordingRestoreV5(None).is_clock_tap_on is None
    assert _RecordingRestoreV5(0).is_clock_tap_on is True
    assert _RecordingRestoreV5(RIOT_FLAGS_CLOCK_IGNORE_TAP).is_clock_tap_on is False
