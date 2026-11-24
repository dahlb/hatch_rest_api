"""Mixin for registering and notifying state-change callbacks."""

from collections.abc import Callable
import logging

_LOGGER = logging.getLogger(__name__)


class CallbacksMixin:
    """Track callbacks and notify them when device state changes."""

    device_name: str
    _callbacks: set[Callable[[], None]]

    def _setup_callbacks(self) -> None:
        self._callbacks = set()

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to run when the device publishes updates."""
        if not hasattr(self, "_callbacks"):
            self._setup_callbacks()
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove a previously registered callback."""
        if not hasattr(self, "_callbacks"):
            self._setup_callbacks()
        self._callbacks.discard(callback)

    def publish_updates(self) -> None:
        """Run every registered callback."""
        if not hasattr(self, "_callbacks"):
            self._setup_callbacks()
        _LOGGER.debug("%s publishing updates", self.device_name)
        for callback in self._callbacks:
            callback()
