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

from .callbacks import CallbacksMixin

_LOGGER = logging.getLogger(__name__)


class ShadowClientSubscriberMixin(CallbacksMixin):
    document_version: int = -1

    def __init__(
        self, device_name: str, thing_name: str, shadow_client: IotShadowClient
    ):
        self.device_name = device_name
        self.thing_name = thing_name
        self.shadow_client = shadow_client
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
        update_accepted_subscribed_future.result()
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
        get_accepted_subscribed_future.result()
        _LOGGER.debug(
            f"unsubscribe_topic_to_update_shadow_accepted: {unsubscribe_topic_to_get_shadow_accepted}"
        )
        self.refresh()

    def _on_update_shadow_accepted(self, response: UpdateShadowResponse):
        _LOGGER.debug(f"update {self.device_name}, RESPONSE: {response}")
        if response.version < self.document_version:
            return
        if response.state:
            if response.state.reported:
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
        ).result()

    def refresh(self):
        _LOGGER.debug("Requesting current shadow state...")
        result = self.shadow_client.publish_get_shadow(
            request=iotshadow.GetShadowRequest(
                thing_name=self.thing_name, client_token=None
            ),
            qos=mqtt.QoS.AT_LEAST_ONCE,
        ).result()
        _LOGGER.debug(f"result: {result}")
