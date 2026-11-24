"""Tests for the RestoreV5 clock turn-off mode helper."""

from typing import Any

import pytest

from hatch_rest_api.const import (
    CLOCK_TURN_OFF_MODE_ALWAYS,
    CLOCK_TURN_OFF_MODE_CUSTOM,
    CLOCK_TURN_OFF_MODE_NEVER,
    RIOT_FLAGS_CLOCK_IGNORE_TAP,
    RIOT_FLAGS_CLOCK_ON,
)
from hatch_rest_api.restore_v5 import RestoreV5


class _RecordingRestoreV5(RestoreV5):
    """RestoreV5 that records desired-state updates instead of publishing them."""

    def __init__(self, flags: int) -> None:
        self.flags = flags
        self.updates: list[dict[str, Any]] = []

    def _update(self, desired_state: dict[str, Any]) -> None:
        self.updates.append(desired_state)


def test_always_clears_clock_on_flag() -> None:
    """``always`` clears only the clock-on bit and sends the mode."""
    device = _RecordingRestoreV5(RIOT_FLAGS_CLOCK_ON | RIOT_FLAGS_CLOCK_IGNORE_TAP)
    device.set_clock_turn_off_mode(CLOCK_TURN_OFF_MODE_ALWAYS)
    assert device.updates == [
        {"clock": {"flags": RIOT_FLAGS_CLOCK_IGNORE_TAP, "turnOffMode": "always"}}
    ]


@pytest.mark.parametrize("mode", [CLOCK_TURN_OFF_MODE_NEVER, CLOCK_TURN_OFF_MODE_CUSTOM])
def test_never_and_custom_set_clock_on_flag(mode: str) -> None:
    """``never`` and ``custom`` set only the clock-on bit and send the mode."""
    device = _RecordingRestoreV5(RIOT_FLAGS_CLOCK_IGNORE_TAP)
    device.set_clock_turn_off_mode(mode)
    expected = RIOT_FLAGS_CLOCK_ON | RIOT_FLAGS_CLOCK_IGNORE_TAP
    assert device.updates == [{"clock": {"flags": expected, "turnOffMode": mode}}]


def test_unknown_mode_raises() -> None:
    """An unknown mode raises and sends nothing."""
    device = _RecordingRestoreV5(0)
    with pytest.raises(ValueError, match="bogus"):
        device.set_clock_turn_off_mode("bogus")
    assert device.updates == []
