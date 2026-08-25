import logging

from awscrt import mqtt
from awsiot import iotshadow
from awsiot.iotshadow import (
    IotShadowClient,
    GetShadowResponse,
    UpdateShadowResponse,
    UpdateShadowRequest,
    ShadowState,
)

from .types import SoundContent, SimpleSoundContent

from .callbacks import CallbacksMixin

_LOGGER = logging.getLogger(__name__)

# Seconds to wait for MQTT operations before giving up. Prevents thread pool
# workers from blocking indefinitely when the connection is down.
MQTT_TIMEOUT = 10


class ShadowClientSubscriberMixin(CallbacksMixin):
    document_version: int = -1

    def __init__(
        self,
        device_name: str,
        thing_name: str,
        mac: str,
        shadow_client: IotShadowClient,
        favorites: list | None = None,
        sounds: list[SoundContent | SimpleSoundContent] | None = None,
    ):
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
        self.sounds_by_id = {s['id']: s for s in sounds if s.get('id')}
        self.sounds_by_name = {s['title']: s for s in sounds if s.get('title')}
        self._subscribed_topics: list[str] = []
        _LOGGER.debug(f"creating {self.__class__.__name__}: {device_name}")

        def update_shadow_accepted(response: UpdateShadowResponse):
            self._on_update_shadow_accepted(response)

        (
            update_accepted_subscribed_future,
            unsubscribe_topic_to_update_shadow_accepted,
        ) = shadow_client.subscribe_to_update_shadow_accepted(
            request=iotshadow.UpdateShadowSubscriptionRequest(
                thing_name=self.thing_name
            ),
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=update_shadow_accepted,
        )
        update_accepted_subscribed_future.result(timeout=MQTT_TIMEOUT)
        self._subscribed_topics.append(unsubscribe_topic_to_update_shadow_accepted)
        _LOGGER.debug(
            f"unsubscribe_topic_to_update_shadow_accepted: {unsubscribe_topic_to_update_shadow_accepted}"
        )

        def on_get_shadow_accepted(response: GetShadowResponse):
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
            f"unsubscribe_topic_to_update_shadow_accepted: {unsubscribe_topic_to_get_shadow_accepted}"
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
            except Exception as error:
                _LOGGER.warning(
                    f"unsubscribing {self.device_name} from {topic} failed: {error}"
                )

    def _on_update_shadow_accepted(self, response: UpdateShadowResponse):
        _LOGGER.debug(f"update {self.device_name}, RESPONSE: {response}")
        if response.version < self.document_version:
            _LOGGER.debug(f'ignoring update {self.device_name}, response version: {response.version} < document version: {self.document_version}')
            return
        if response.state:
            if response.state.reported:
                _LOGGER.debug(f'updating {self.device_name} local state: {response.state.reported}')
                self.document_version = response.version
                self._update_local_state(response.state.reported)

    def _on_get_shadow_accepted(self, response: GetShadowResponse):
        _LOGGER.debug(f"get {self.device_name}, RESPONSE: {response}")
        if response.version < self.document_version:
            return
        if response.state:
            if response.state.delta:
                pass

            if response.state.reported:
                self.document_version = response.version
                self._update_local_state(response.state.reported)

    def _update(self, desired_state):
        _LOGGER.debug(f"updating: {desired_state}")
        request: UpdateShadowRequest = UpdateShadowRequest(
            thing_name=self.thing_name,
            state=ShadowState(
                desired=desired_state,
            ),
        )
        self.shadow_client.publish_update_shadow(
            request, mqtt.QoS.AT_LEAST_ONCE
        ).result(timeout=MQTT_TIMEOUT)

    def refresh(self):
        _LOGGER.debug("Requesting current shadow state...")
        result = self.shadow_client.publish_get_shadow(
            request=iotshadow.GetShadowRequest(
                thing_name=self.thing_name, client_token=None
            ),
            qos=mqtt.QoS.AT_LEAST_ONCE,
        ).result(timeout=MQTT_TIMEOUT)
        _LOGGER.debug(f"result: {result}")
