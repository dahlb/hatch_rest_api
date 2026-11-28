"""async_command, async_refresh and async_unsubscribe publish without blocking the event loop."""

import asyncio
from concurrent.futures import Future
import threading
import time
from typing import Any
from unittest.mock import patch

import pytest

from hatch_rest_api import (
    RestBaby,
    RestIot,
    RestMini,
    RestoreIot,
    RestoreV5,
    RestPlus,
    shadow_client_subscriber as subscriber_module,
)
from hatch_rest_api.const import CUSTOM_COLOR_ID
from hatch_rest_api.shadow_client_subscriber import ShadowClientSubscriberMixin


class ThreadedShadowClient:
    """Shadow client whose futures complete on another thread, as awscrt's do."""

    def __init__(self, delay: float = 0.05, fail: bool = False, never: bool = False) -> None:
        """Complete each future after ``delay``; fail or never complete it if asked."""
        self.delay, self.fail, self.never = delay, fail, never
        self.published: list[dict[str, Any]] = []
        self.got: list[str] = []
        self.unsubscribed: list[str] = []
        self.completed_on: list[str] = []

    def _future(self) -> Future[Any]:
        future: Future[Any] = Future()
        if self.never:
            return future

        def complete() -> None:
            time.sleep(self.delay)
            self.completed_on.append(threading.current_thread().name)
            if self.fail:
                future.set_exception(RuntimeError("publish failed"))
            else:
                future.set_result(None)

        threading.Thread(target=complete, name="fake-crt").start()
        return future

    def publish_update_shadow(self, request: Any, qos: Any) -> Future[Any]:
        """Record the desired state and return a pending future."""
        self.published.append(request.state.desired)
        return self._future()

    def publish_get_shadow(self, request: Any, qos: Any) -> Future[Any]:
        """Record the request and return a pending future."""
        self.got.append(request.thing_name)
        return self._future()

    def unsubscribe(self, topic: str) -> Future[Any]:
        """Record the topic and return a pending future."""
        self.unsubscribed.append(topic)
        return self._future()


def _device[T: ShadowClientSubscriberMixin](
    cls: type[T], client: ThreadedShadowClient, **attributes: Any
) -> T:
    device = cls.__new__(cls)
    device.device_name, device.thing_name, device.mac = "Nursery", "thing-123", "AA"
    device.shadow_client = client
    device.favorites, device.sounds = [], []
    device.sounds_by_id, device.sounds_by_name = {}, {}
    device._subscribed_topics = ["topic/a", "topic/b"]
    for name, value in attributes.items():
        setattr(device, name, value)
    return device


def _sync_payloads(device: ShadowClientSubscriberMixin, command: str, *args: Any) -> list[Any]:
    """The updates the synchronous command sends, for comparison."""
    sent: list[Any] = []
    with patch.object(type(device), "_update", lambda self, desired: sent.append(desired)):
        getattr(device, command)(*args)
    return sent


COMMANDS = [
    (RestMini, "set_volume", (40,)),
    (RestPlus, "set_color", (255, 0, 0, 50)),
    (RestIot, "set_color", (0, 255, 0, 0, 30)),
    (RestIot, "turn_light_off", ()),
    (RestBaby, "set_toddler_lock", (True,)),
    (RestoreIot, "set_clock", (40,)),
    (RestoreV5, "set_clock", (80, 10)),
    (RestoreV5, "clock_tap_on", ()),
]


@pytest.mark.parametrize(("cls", "command", "args"), COMMANDS)
async def test_publishes_what_the_sync_command_sends(
    cls: type[ShadowClientSubscriberMixin], command: str, args: tuple[Any, ...]
) -> None:
    """async_command sends exactly the updates the synchronous command would."""
    client = ThreadedShadowClient()
    device = _device(cls, client, current_playing="remote", color_id=CUSTOM_COLOR_ID)
    expected = _sync_payloads(
        _device(cls, ThreadedShadowClient(), current_playing="remote", color_id=CUSTOM_COLOR_ID),
        command,
        *args,
    )

    await device.async_command(getattr(device, command), *args)

    assert expected
    assert client.published == expected
    assert client.completed_on == ["fake-crt"] * len(expected)


async def test_does_not_block_the_event_loop() -> None:
    """Other tasks keep running while the update waits for its acknowledgement."""
    client = ThreadedShadowClient(delay=0.2)
    device = _device(RestMini, client)
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    await device.async_command(device.set_volume, 50)
    task.cancel()

    # A blocking .result() would have frozen the loop for the whole 0.2s.
    assert ticks >= 5


async def test_keyword_arguments_and_several_updates_in_order() -> None:
    """Keyword arguments pass through, and multiple updates are sent in order."""

    class TwoStepMini(RestMini):
        def two_steps(self, first: int, *, second: int) -> None:
            self.set_volume(first)
            self.set_volume(second)

    client = ThreadedShadowClient()
    device = _device(TwoStepMini, client)
    await device.async_command(device.two_steps, 10, second=90)
    assert [update["current"]["sound"]["v"] for update in client.published] == [6554, 58982]


async def test_timeout_when_mqtt_never_acknowledges() -> None:
    """An update MQTT never acknowledges raises TimeoutError after MQTT_TIMEOUT."""
    device = _device(RestMini, ThreadedShadowClient(never=True))
    with patch.object(subscriber_module, "MQTT_TIMEOUT", 0.05), pytest.raises(TimeoutError):
        await device.async_command(device.set_volume, 50)


async def test_publish_failure_is_raised() -> None:
    """A failed publish raises the error the future carries."""
    device = _device(RestMini, ThreadedShadowClient(fail=True))
    with pytest.raises(RuntimeError, match="publish failed"):
        await device.async_command(device.set_volume, 50)


async def test_command_error_sends_nothing_and_sync_still_works() -> None:
    """If the command raises, nothing is sent, and later sync commands publish normally."""
    client = ThreadedShadowClient(delay=0)
    device = _device(RestIot, client)
    with pytest.raises(ValueError):
        await device.async_command(device.set_favorite, "no-number-here")
    assert client.published == []

    device.set_volume(20)
    assert client.published == [{"current": {"sound": {"v": 13107}}}]


async def test_rejects_another_devices_method() -> None:
    """Only this device's own methods are accepted."""
    client = ThreadedShadowClient()
    device, other = _device(RestMini, client), _device(RestMini, client)
    with pytest.raises(ValueError, match="command method of this device"):
        await device.async_command(other.set_volume, 50)
    assert client.published == []


async def test_rejects_an_already_async_method() -> None:
    """Async methods are awaited directly, not passed to async_command."""
    device = _device(RestoreV5, ThreadedShadowClient())
    with pytest.raises(TypeError, match="already async"):
        await device.async_command(device.refresh_alarms)


async def test_async_refresh() -> None:
    """async_refresh requests the shadow and awaits the acknowledgement."""
    client = ThreadedShadowClient()
    device = _device(RestMini, client)
    await device.async_refresh()
    assert client.got == ["thing-123"]
    assert client.completed_on == ["fake-crt"]


async def test_async_unsubscribe() -> None:
    """async_unsubscribe releases every topic, even when one fails."""
    client = ThreadedShadowClient(fail=True)
    device = _device(RestMini, client)
    await device.async_unsubscribe()
    assert sorted(client.unsubscribed) == ["topic/a", "topic/b"]
    assert device._subscribed_topics == []


async def test_timeout_leaves_the_mqtt_future_for_awscrt_to_complete() -> None:
    """Giving up on an acknowledgement doesn't cancel awscrt's future.

    awscrt completes it later from its own thread; set_result() on a cancelled
    future would raise InvalidStateError on that thread.
    """
    client = ThreadedShadowClient(never=True)
    device = _device(RestMini, client)
    pending: list[Future[Any]] = []
    publish = client.publish_update_shadow

    def keep_future(request: Any, qos: Any) -> Future[Any]:
        future = publish(request, qos)
        pending.append(future)
        return future

    client.publish_update_shadow = keep_future  # type: ignore[method-assign]
    with patch.object(subscriber_module, "MQTT_TIMEOUT", 0.05), pytest.raises(TimeoutError):
        await device.async_command(device.set_volume, 50)

    assert not pending[0].cancelled()
    pending[0].set_result(None)  # what awscrt does when the PUBACK finally arrives


async def test_cancelling_the_caller_leaves_the_mqtt_future_alone() -> None:
    """Cancelling the task awaiting a command doesn't cancel awscrt's future either."""
    client = ThreadedShadowClient(never=True)
    device = _device(RestMini, client)
    pending: list[Future[Any]] = []
    publish = client.publish_update_shadow

    def keep_future(request: Any, qos: Any) -> Future[Any]:
        future = publish(request, qos)
        pending.append(future)
        return future

    client.publish_update_shadow = keep_future  # type: ignore[method-assign]
    task = asyncio.create_task(device.async_command(device.set_volume, 50))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not pending[0].cancelled()
    pending[0].set_result(None)
