"""Builders for device objects that record shadow updates instead of sending them."""

from typing import Any, cast
from unittest.mock import MagicMock

from hatch_rest_api.shadow_client_subscriber import ShadowClientSubscriberMixin


def recording_device[T: ShadowClientSubscriberMixin](
    cls: type[T],
    sounds: list[Any] | None = None,
    favorites: list[Any] | None = None,
    **attributes: Any,
) -> T:
    """Return a ``cls`` device with no MQTT connection.

    Every desired-state update the device would publish is recorded, see
    ``sent()``, and a mock callback is registered, see ``listener()``.

    Args:
        cls: Device class to build.
        sounds: Sound content to give the device.
        favorites: Favorites to give the device.
        **attributes: Attributes to set on the device, e.g. ``current_playing``.
    """
    device = cls.__new__(cls)
    device.device_name = "Nursery"
    device.thing_name = "thing-123"
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.favorites = favorites or []
    device.sounds = sounds or []
    device.sounds_by_id = {s["id"]: s for s in device.sounds if s.get("id")}
    device.sounds_by_name = {s["title"]: s for s in device.sounds if s.get("title")}
    updates: list[dict[str, Any]] = []
    setattr(device, "_sent", updates)  # noqa: B010 - not a declared attribute
    setattr(device, "_update", updates.append)  # noqa: B010 - replaces the MQTT publish
    callback = MagicMock()
    setattr(device, "_listener", callback)  # noqa: B010 - not a declared attribute
    device.register_callback(callback)
    for name, value in attributes.items():
        setattr(device, name, value)
    return device


def sent(device: ShadowClientSubscriberMixin) -> list[dict[str, Any]]:
    """Return the shadow updates a ``recording_device`` would have published."""
    return cast("list[dict[str, Any]]", getattr(device, "_sent"))  # noqa: B009


def listener(device: ShadowClientSubscriberMixin) -> MagicMock:
    """Return the mock callback registered on a ``recording_device``."""
    return cast("MagicMock", getattr(device, "_listener"))  # noqa: B009


FAVORITES = [
    {"id": 101, "name": "Bedtime", "active": True},
    {"id": 102, "name": "Nap", "active": False},
]
