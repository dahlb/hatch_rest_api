"""Devices run, add and remove state-change callbacks."""

from unittest.mock import MagicMock

from hatch_rest_api import RestMini

from .device_fakes import listener, recording_device


def test_publish_runs_every_callback() -> None:
    """publish_updates calls each registered callback once."""
    device = recording_device(RestMini)
    other = MagicMock()
    device.register_callback(other)
    device.publish_updates()
    listener(device).assert_called_once_with()
    other.assert_called_once_with()


def test_removed_callback_is_not_called() -> None:
    """A removed callback is no longer called."""
    device = recording_device(RestMini)
    device.remove_callback(listener(device))
    device.publish_updates()
    listener(device).assert_not_called()


def test_callbacks_work_before_any_are_registered() -> None:
    """Removing or publishing on a fresh device doesn't fail."""
    device = RestMini.__new__(RestMini)
    device.device_name = "Nursery"
    device.remove_callback(MagicMock())
    device.publish_updates()
    callback = MagicMock()
    device.register_callback(callback)
    device.publish_updates()
    callback.assert_called_once_with()
