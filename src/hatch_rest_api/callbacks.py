from collections.abc import Callable
import logging

_LOGGER = logging.getLogger(__name__)


class CallbacksMixin:
    def _setup_callbacks(self) -> None:
        self._callbacks: set[Callable[[], None]] = set()

    def register_callback(self, callback: Callable[[], None]) -> None:
        if not hasattr(self, "_callbacks"):
            self._setup_callbacks()
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        if not hasattr(self, "_callbacks"):
            self._setup_callbacks()
        self._callbacks.discard(callback)

    def publish_updates(self) -> None:
        if not hasattr(self, "_callbacks"):
            self._setup_callbacks()
        _LOGGER.debug(f"{self.device_name} publishing updates")
        for callback in self._callbacks:
            callback()
