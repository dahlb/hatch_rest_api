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

from .util import convert_to_percentage, safely_get_json_value, convert_from_percentage
from .callbacks import CallbacksMixin
from .const import RestMiniAudioTrack

_LOGGER = logging.getLogger(__name__)


class RestMini(CallbacksMixin):
    firmware_version: str = None
    is_playing: bool = None
    audio_track: int = None
    volume: int = None
    document_version: int = -1

    def __init__(
        self, device_name: str, thing_name: str, shadow_client: IotShadowClient
    ):
        self.device_name = device_name
        self.thing_name = thing_name
        self.shadow_client = shadow_client
        _LOGGER.debug(f"creating rest mini: {device_name}")

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
        _LOGGER.debug(f"unsubscribe_topic_to_update_shadow_accepted: {unsubscribe_topic_to_update_shadow_accepted}")

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
        _LOGGER.debug(f"unsubscribe_topic_to_update_shadow_accepted: {unsubscribe_topic_to_get_shadow_accepted}")
        self.refresh()

    def refresh(self):
        _LOGGER.debug("Requesting current shadow state...")
        result = self.shadow_client.publish_get_shadow(
            request=iotshadow.GetShadowRequest(
                thing_name=self.thing_name, client_token=None
            ),
            qos=mqtt.QoS.AT_LEAST_ONCE,
        ).result()
        _LOGGER.debug(f"result: {result}")

    def _update_local_state(self, state):
        _LOGGER.debug(f"update local state: {self.device_name}, {state}")
        if safely_get_json_value(state, "deviceInfo.f"):
            self.firmware_version = safely_get_json_value(state, "deviceInfo.f")
        if safely_get_json_value(state, "current.sound.id"):
            self.audio_track = RestMiniAudioTrack(
                safely_get_json_value(state, "current.sound.id")
            )
        if safely_get_json_value(state, "current.playing"):
            self.is_playing = safely_get_json_value(state, "current.playing") != "none"
        if safely_get_json_value(state, "current.sound.v"):
            self.volume = convert_to_percentage(
                safely_get_json_value(state, "current.sound.v")
            )
        self.publish_updates()

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

    def __repr__(self):
        return {
            "device_name": self.device_name,
            "thing_name": self.thing_name,
            "firmware_version": self.firmware_version,
            "is_playing": self.is_playing,
            "audio_track": self.audio_track,
            "volume": self.volume,
            "document_version": self.document_version,
        }

    def __str__(self):
        return f"{self.__repr__()}"

    def _update(self, desired_state):
        request: UpdateShadowRequest = UpdateShadowRequest(
            thing_name=self.thing_name,
            state=ShadowState(
                desired=desired_state,
            ),
        )
        self.shadow_client.publish_update_shadow(
            request, mqtt.QoS.AT_LEAST_ONCE
        ).result()

    def set_volume(self, percentage: int):
        self._update(
            {
                "current": {
                    "sound": {
                        "v": convert_from_percentage(percentage),
                    },
                },
            }
        )

    def set_audio_track(self, audio_track: RestMiniAudioTrack):
        if audio_track == RestMiniAudioTrack.NONE:
            self._update(
                {
                    "current": {
                        "playing": "none",
                        "step": 0,
                    },
                }
            )
        else:
            self._update(
                {
                    "current": {
                        "playing": "remote",
                        "step": 1,
                        "sound": {
                            "id": audio_track.value,
                            "until": "indefinite",
                        },
                    },
                }
            )
