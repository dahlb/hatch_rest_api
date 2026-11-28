"""The shared IotDevice base keeps each device class's public surface unchanged.

The Home Assistant integration detects device features with ``isinstance`` and
``hasattr`` (for example ``isinstance(device, RestIot)`` before ``stop_sound``, and
``hasattr(device, "clock_nighttime")``). These tests pin the invariants that keep
that working: the classes stay siblings, and the base classes don't give a device
a member it didn't have.
"""

import itertools

import pytest

from hatch_rest_api import RestBaby, RestIot, RestoreIot, RestoreV4, RestoreV5
from hatch_rest_api.iot_device import Clock24HourMixin, IotDevice, IotRestDevice, IotSoundDevice

CLASSES = [RestIot, RestBaby, RestoreIot, RestoreV5]


@pytest.mark.parametrize(("a", "b"), list(itertools.permutations(CLASSES, 2)))
def test_device_classes_are_siblings(a: type[IotDevice], b: type[IotDevice]) -> None:
    """No device class is a subclass of another, so isinstance checks stay exact."""
    assert not issubclass(a, b)


def test_restore_v4_is_still_a_restore_v5() -> None:
    """RestoreV4 keeps subclassing RestoreV5, which integrations rely on."""
    assert issubclass(RestoreV4, RestoreV5)


@pytest.mark.parametrize("cls", CLASSES)
def test_every_device_is_an_iot_device(cls: type[IotDevice]) -> None:
    """All four share the base."""
    assert issubclass(cls, IotDevice)


@pytest.mark.parametrize(
    ("cls", "missing"),
    [
        # RestoreIot has no sound commands or favorite progress.
        (RestoreIot, ["set_sound", "set_audio_track", "current_id", "current_step"]),
        # RestoreV5 reports no audio track or charging status, and has no single clock level.
        (RestoreV5, ["audio_track", "charging_status", "battery_level"]),
        # RestBaby has no 24-hour clock flag or stop_sound.
        (RestBaby, ["is_clock_24h", "stop_sound"]),
        # Only RestoreV5 has the dual clock brightness and schedule.
        (RestIot, ["clock_nighttime", "clock_daytime", "clock_turn_off_mode"]),
        (RestBaby, ["clock_nighttime", "clock_daytime", "clock_turn_off_mode"]),
        (RestoreIot, ["clock_nighttime", "clock_daytime", "clock_turn_off_mode"]),
        # Toddler lock and battery are Rest-only.
        (RestoreIot, ["set_toddler_lock", "toddler_lock", "battery_level"]),
        (RestoreV5, ["set_toddler_lock", "toddler_lock"]),
    ],
)
def test_base_adds_no_members(cls: type[IotDevice], missing: list[str]) -> None:
    """Members a device never had stay absent."""
    present = [name for name in missing if hasattr(cls, name)]
    assert present == []


def test_set_sound_only_where_it_was() -> None:
    """IotSoundDevice is used by exactly the classes that had set_sound."""
    assert [cls.__name__ for cls in CLASSES if issubclass(cls, IotSoundDevice)] == [
        "RestIot",
        "RestBaby",
        "RestoreV5",
    ]


def test_rest_family_base_only_for_the_rests() -> None:
    """IotRestDevice is used by exactly RestIot and RestBaby."""
    assert [cls.__name__ for cls in CLASSES if issubclass(cls, IotRestDevice)] == [
        "RestIot",
        "RestBaby",
    ]


def test_24_hour_clock_only_where_it_was() -> None:
    """Clock24HourMixin is used by exactly the classes that had is_clock_24h."""
    assert [cls.__name__ for cls in CLASSES if issubclass(cls, Clock24HourMixin)] == [
        "RestIot",
        "RestoreIot",
        "RestoreV5",
    ]
