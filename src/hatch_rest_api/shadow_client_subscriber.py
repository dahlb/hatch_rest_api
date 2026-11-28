"""Base class for devices whose state is synced through an AWS IoT device shadow."""

import logging
from typing import TYPE_CHECKING, Any

from awscrt import mqtt
from awsiot import iotshadow
from awsiot.iotshadow import (
    GetShadowResponse,
    IotShadowClient,
    ShadowState,
    UpdateShadowRequest,
    UpdateShadowResponse,
)

from .callbacks import CallbacksMixin
from .types import SimpleSoundContent, SoundContent

_LOGGER = logging.getLogger(__name__)

# Seconds to wait for MQTT operations before giving up. Prevents thread pool
# workers from blocking indefinitely when the connection is down.
MQTT_TIMEOUT = 10


class ShadowClientSubscriberMixin(CallbacksMixin):
    """Device base class that mirrors an AWS IoT device shadow.

    Subclasses implement ``_update_local_state`` to map the reported shadow state onto
    their attributes, and call ``_update`` to request state changes.
    """

    document_version: int = -1

    if TYPE_CHECKING:
        # Implemented by every device subclass.
        def _update_local_state(self, state: dict[str, Any]) -> None: ...

    def as_dict(self) -> dict[str, Any]:
        """Return the device state as a dictionary, for diagnostics and debugging.

        Device classes extend this with their own state.
        """
        return {
            "device_name": self.device_name,
            "thing_name": self.thing_name,
            "mac": self.mac,
            "document_version": self.document_version,
        }

    def __repr__(self) -> str:
        """Return a short description naming the device."""
        device_name = getattr(self, "device_name", None)
        thing_name = getattr(self, "thing_name", None)
        return f"<{type(self).__name__} device_name={device_name!r} thing_name={thing_name!r}>"

    def __str__(self) -> str:
        """Return the device state as a string."""
        return str(self.as_dict())

    def __init__(
        self,
        device_name: str,
        thing_name: str,
        mac: str,
        shadow_client: IotShadowClient,
        favorites: list[Any] | None = None,
        sounds: list[SoundContent | SimpleSoundContent] | None = None,
    ) -> None:
        """Subscribe to the device shadow and request its current state.

        Args:
            device_name: Display name of the device.
            thing_name: AWS IoT thing name of the device.
            mac: MAC address of the device.
            shadow_client: Connected AWS IoT shadow client.
            favorites: Favorites configured on the device, if any.
            sounds: Sound content available to the device, if any.
        """
        if favorites is None:
            favorites = []
        if sounds is None:
            sounds = list[SoundContent | SimpleSoundContent]()
        self.device_name = device_name
        self.thing_name = thing_name
        self.mac = mac
        self.shadow_client = shadow_client
        self.favorites = favorites
        self.sounds = sounds
        self.sounds_by_id = {s["id"]: s for s in sounds if s.get("id")}
        self.sounds_by_name = {s["title"]: s for s in sounds if s.get("title")}
        self._subscribed_topics: list[str] = []
        _LOGGER.debug("creating %s: %s", self.__class__.__name__, device_name)

        def update_shadow_accepted(response: UpdateShadowResponse) -> None:
            self._on_update_shadow_accepted(response)

        (
            update_accepted_subscribed_future,
            unsubscribe_topic_to_update_shadow_accepted,
        ) = shadow_client.subscribe_to_update_shadow_accepted(
            request=iotshadow.UpdateShadowSubscriptionRequest(thing_name=self.thing_name),
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=update_shadow_accepted,
        )
        update_accepted_subscribed_future.result(timeout=MQTT_TIMEOUT)
        self._subscribed_topics.append(unsubscribe_topic_to_update_shadow_accepted)
        _LOGGER.debug(
            "unsubscribe_topic_to_update_shadow_accepted: %s",
            unsubscribe_topic_to_update_shadow_accepted,
        )

        def on_get_shadow_accepted(response: GetShadowResponse) -> None:
            self._on_get_shadow_accepted(response)

        (
            get_accepted_subscribed_future,
            unsubscribe_topic_to_get_shadow_accepted,
        ) = shadow_client.subscribe_to_get_shadow_accepted(
            request=iotshadow.GetShadowSubscriptionRequest(thing_name=self.thing_name),
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_get_shadow_accepted,
        )
        get_accepted_subscribed_future.result(timeout=MQTT_TIMEOUT)
        self._subscribed_topics.append(unsubscribe_topic_to_get_shadow_accepted)
        _LOGGER.debug(
            "unsubscribe_topic_to_update_shadow_accepted: %s",
            unsubscribe_topic_to_get_shadow_accepted,
        )
        self.refresh()

    def unsubscribe(self) -> None:
        """Drop the shadow subscriptions this device registered.

        awscrt holds a reference from native code to every subscription
        callback, and both callbacks above close over ``self``. Those native
        references are invisible to Python's garbage collector, so until the
        subscriptions are released nothing can reclaim the device, its shadow
        client, or the TLS context and MQTT buffers underneath -- not even
        after ``disconnect()`` has closed the socket and every Python caller
        has dropped its reference.

        Callers that rebuild the connection therefore have to call this first.
        ha_hatch rebuilds hourly, when the AWS credentials expire, so skipping
        it stranded one full connection graph per hour for the life of the
        process.

        Blocks, so call it off the event loop. Safe to call more than once, and
        safe to call on a connection that has already dropped: the topics are
        discarded either way, because tearing the connection down releases the
        same native references that a clean UNSUBACK would.
        """
        while self._subscribed_topics:
            topic = self._subscribed_topics.pop()
            try:
                self.shadow_client.unsubscribe(topic).result(timeout=MQTT_TIMEOUT)
            except Exception as error:  # noqa: BLE001 - keep releasing the remaining topics
                _LOGGER.warning(
                    "unsubscribing %s from %s failed: %s", self.device_name, topic, error
                )

    def _on_update_shadow_accepted(self, response: UpdateShadowResponse) -> None:
        _LOGGER.debug("update %s, RESPONSE: %s", self.device_name, response)
        if response.version < self.document_version:
            _LOGGER.debug(
                "ignoring update %s, response version: %s < document version: %s",
                self.device_name,
                response.version,
                self.document_version,
            )
            return
        if response.state and response.state.reported:
            _LOGGER.debug("updating %s local state: %s", self.device_name, response.state.reported)
            self.document_version = response.version
            self._update_local_state(response.state.reported)

    def _on_get_shadow_accepted(self, response: GetShadowResponse) -> None:
        _LOGGER.debug("get %s, RESPONSE: %s", self.device_name, response)
        if response.version < self.document_version:
            return
        if response.state:
            if response.state.delta:
                pass

            if response.state.reported:
                self.document_version = response.version
                self._update_local_state(response.state.reported)

    def _update(self, desired_state: dict[str, Any]) -> None:
        _LOGGER.debug("updating: %s", desired_state)
        request: UpdateShadowRequest = UpdateShadowRequest(
            thing_name=self.thing_name,
            state=ShadowState(
                desired=desired_state,
            ),
        )
        self.shadow_client.publish_update_shadow(request, mqtt.QoS.AT_LEAST_ONCE).result(
            timeout=MQTT_TIMEOUT
        )

    def refresh(self) -> None:
        """Request the current shadow state; the response arrives via the subscription."""
        _LOGGER.debug("Requesting current shadow state...")
        result = self.shadow_client.publish_get_shadow(
            request=iotshadow.GetShadowRequest(thing_name=self.thing_name, client_token=None),
            qos=mqtt.QoS.AT_LEAST_ONCE,
        ).result(timeout=MQTT_TIMEOUT)
        _LOGGER.debug("result: %s", result)
