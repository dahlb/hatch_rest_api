"""Tests for the RestoreV5 clock schedule time helpers."""

from datetime import time
from typing import Any

from hatch_rest_api.restore_v5 import RestoreV5


class _RecordingRestoreV5(RestoreV5):
    """RestoreV5 that records desired-state updates instead of publishing them."""

    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def _update(self, desired_state: dict[str, Any]) -> None:
        self.updates.append(desired_state)


def test_set_clock_turn_on_at_writes_on_and_bright() -> None:
    """The turn-on time is written to both ``turnOnAt`` and ``turnBrightAt``."""
    device = _RecordingRestoreV5()
    device.set_clock_turn_on_at(time(6, 30))
    assert device.updates == [{"clock": {"turnOnAt": "06:30:00", "turnBrightAt": "06:30:00"}}]


def test_set_clock_turn_off_at_writes_off_and_dim() -> None:
    """The turn-off time is written to both ``turnOffAt`` and ``turnDimAt``."""
    device = _RecordingRestoreV5()
    device.set_clock_turn_off_at(time(19, 45, 15))
    assert device.updates == [{"clock": {"turnOffAt": "19:45:15", "turnDimAt": "19:45:15"}}]
