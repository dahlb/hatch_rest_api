"""Every device class has a string repr and a dict of its state."""

import unittest

from hatch_rest_api import (
    RestBaby,
    RestIot,
    RestMini,
    Restore,
    RestoreIot,
    RestoreV4,
    RestoreV5,
    RestPlus,
)
from hatch_rest_api.shadow_client_subscriber import ShadowClientSubscriberMixin

DEVICE_CLASSES: list[type[ShadowClientSubscriberMixin]] = [
    RestMini,
    RestPlus,
    RestIot,
    RestBaby,
    RestoreIot,
    RestoreV4,
    RestoreV5,
]
# The original Restore's as_dict() needs state set in __init__; test_restore covers it.
REPR_CLASSES: list[type[ShadowClientSubscriberMixin]] = [Restore, *DEVICE_CLASSES]


def bare_device[T: ShadowClientSubscriberMixin](cls: type[T]) -> T:
    """A device of ``cls`` with identity set and no shadow connection."""
    device = cls.__new__(cls)
    device.device_name = "Nursery"
    device.thing_name = "thing-123"
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.sounds = []
    device.favorites = []
    return device


class DeviceReprTest(unittest.TestCase):
    """repr() is a short string; as_dict() and str() carry the state."""

    def test_repr_is_a_short_string(self) -> None:
        """repr() works and names the class and device."""
        for cls in REPR_CLASSES:
            with self.subTest(cls=cls.__name__):
                assert (
                    repr(bare_device(cls))
                    == f"<{cls.__name__} device_name='Nursery' thing_name='thing-123'>"
                )

    def test_repr_before_init(self) -> None:
        """repr() works on a device that has no identity set yet."""
        for cls in REPR_CLASSES:
            with self.subTest(cls=cls.__name__):
                assert repr(cls.__new__(cls)) == (
                    f"<{cls.__name__} device_name=None thing_name=None>"
                )

    def test_as_dict_carries_the_identity(self) -> None:
        """as_dict() is a dict that starts with the device identity."""
        for cls in DEVICE_CLASSES:
            with self.subTest(cls=cls.__name__):
                state = bare_device(cls).as_dict()
                assert isinstance(state, dict)
                assert state["device_name"] == "Nursery"
                assert state["thing_name"] == "thing-123"
                assert state["mac"] == "AA:BB:CC:DD:EE:FF"
                assert "document_version" in state

    def test_str_is_the_state(self) -> None:
        """str() is the as_dict() state, as before."""
        for cls in DEVICE_CLASSES:
            with self.subTest(cls=cls.__name__):
                device = bare_device(cls)
                assert str(device) == str(device.as_dict())
