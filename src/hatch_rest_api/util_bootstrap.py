import logging
import asyncio

from functools import partial
from awscrt import io
from awscrt.auth import AwsCredentialsProvider
from awsiot.mqtt_connection_builder import websockets_with_default_aws_signing
from awsiot.iotshadow import IotShadowClient
from aiohttp import ClientSession
from uuid import uuid4
from re import sub, IGNORECASE

from . import BaseError
from .const import NO_SOUND_ID
from .contentful import Contentful
from .hatch import Hatch
from .aws_http import AwsHttp
from .rest_mini import RestMini
from .rest_plus import RestPlus
from .rest_iot import RestIot
from .restore_iot import RestoreIot
from .restore_v5 import RestoreV5
from .types import SimpleSoundContent

_LOGGER = logging.getLogger(__name__)


async def get_rest_devices(
    email: str,
    password: str,
    client_session: ClientSession = None,
    on_connection_interrupted=None,
    on_connection_resumed=None,
):
    loop = asyncio.get_running_loop()
    if _LOGGER.isEnabledFor(logging.DEBUG):
        await loop.run_in_executor(None, io.init_logging, io.LogLevel.Debug, "hatch_rest_api-aws_mqtt.log")
    api = Hatch(client_session=client_session)
    contentful = Contentful(client_session=client_session)
    token = await api.login(email=email, password=password)
    iot_devices = await api.iot_devices(auth_token=token)
    if len(iot_devices) == 0:
        raise BaseError("No compatible devices found on this hatch account")
    aws_token = await api.token(auth_token=token)
    favorites_map = await _get_favorites_for_all_v2_devices(api, token, iot_devices)
    routines_map = await _get_routines_for_all_v2_devices(api, token, iot_devices)
    sounds_map = await _get_sound_content_for_all_v2_devices(api, token, contentful, iot_devices)
    aws_http: AwsHttp = AwsHttp(api.api_session)
    aws_credentials = await aws_http.aws_credentials(
        region=aws_token["region"],
        identityId=aws_token["identityId"],
        aws_token=aws_token["token"],
    )
    _LOGGER.debug(f"AWS credentials: {aws_credentials}")
    credentials_provider = AwsCredentialsProvider.new_static(
        aws_credentials["Credentials"]["AccessKeyId"],
        aws_credentials["Credentials"]["SecretKey"],
        session_token=aws_credentials["Credentials"]["SessionToken"],
    )
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)
    endpoint = aws_token["endpoint"].lstrip("https://")
    safe_email = sub("[^a-z]", "", email, flags=IGNORECASE).lower()
    mqtt_connection = await loop.run_in_executor(None, partial(websockets_with_default_aws_signing,
                                                               region=aws_token["region"],
                                                               credentials_provider=credentials_provider,
                                                               keep_alive_secs=30,
                                                               client_bootstrap=client_bootstrap,
                                                               endpoint=endpoint,
                                                               client_id=f"hatch_rest_api/{safe_email}/{str(uuid4())}",
                                                               on_connection_interrupted=on_connection_interrupted,
                                                               on_connection_resumed=on_connection_resumed))
    try:
        connect_future = await loop.run_in_executor(None, mqtt_connection.connect)
        await loop.run_in_executor(None, connect_future.result)
        _LOGGER.debug("mqtt connection connected")
    except Exception as e:
        _LOGGER.error(f"MQTT connection failed with exception {e}")
        raise e

    shadow_client = IotShadowClient(mqtt_connection)

    def create_rest_devices(iot_device):
        if iot_device["product"] == "restPlus":
            return RestPlus(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                mac=iot_device["macAddress"],
                shadow_client=shadow_client,
            )
        elif iot_device["product"] in ["riot", "riotPlus"]:
            return RestIot(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                mac=iot_device["macAddress"],
                shadow_client=shadow_client,
                favorites=favorites_map[iot_device["macAddress"]],
                sounds=sounds_map[iot_device["macAddress"]],
            )
        elif iot_device["product"] == "restoreIot":
            return RestoreIot(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                mac=iot_device["macAddress"],
                shadow_client=shadow_client,
                favorites=routines_map[iot_device["macAddress"]] + favorites_map[iot_device["macAddress"]],
                sounds=sounds_map[iot_device["macAddress"]],
            )
        elif iot_device["product"] == "restoreV5":
            return RestoreV5(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                mac=iot_device["macAddress"],
                shadow_client=shadow_client,
                favorites=routines_map[iot_device["macAddress"]] + favorites_map[iot_device["macAddress"]],
                sounds=sounds_map[iot_device["macAddress"]],
            )
        else:
            return RestMini(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                mac=iot_device["macAddress"],
                shadow_client=shadow_client,
            )

    rest_devices = map(create_rest_devices, iot_devices)
    return (
        api,
        mqtt_connection,
        list(rest_devices),
        aws_credentials["Credentials"]["Expiration"],
    )


async def _get_favorites_for_all_v2_devices(api, token, iot_devices):
    mac_to_favorite = {}
    for device in iot_devices:
        if device["product"] in ["riot", "riotPlus", "restoreV5"]:
            mac = device["macAddress"]
            favorites = await api.favorites(auth_token=token, mac=mac)
            _LOGGER.debug(f"Favorites for {mac}: {favorites}")
            mac_to_favorite[mac] = favorites
    return mac_to_favorite


async def _get_routines_for_all_v2_devices(api, token, iot_devices):
    mac_to_routines = {}
    for device in iot_devices:
        if device["product"] in ["riot", "restoreIot", "restoreV5"]:
            mac = device["macAddress"]
            routines = await api.routines(auth_token=token, mac=mac)
            _LOGGER.debug(f"Routines for {mac}: {routines}")
            mac_to_routines[mac] = routines
    return mac_to_routines


async def _get_sound_content_for_all_v2_devices(api: Hatch, token: str, contentful: Contentful, iot_devices) -> dict[str, list[SimpleSoundContent]]:
    mac_to_sounds = {}
    for device in iot_devices:
        mac = device["macAddress"]
        if device["product"] in ["riot", "riotPlus"]:
            content = await api.content(
                auth_token=token, product="riot", content=["sound"]
            )
            sounds =  [s for s in content["contentItems"] if s['id'] != NO_SOUND_ID]
        elif device["product"] == "restoreV5":
            content = await contentful.graphql_query(
                auth_token=token,
                query="""
                    query GetSounds($product: String!) {
                      soundCollection(
                        limit: 1000
                        where: {
                          title_exists: true
                          title_not_contains: "DVT: "
                          wavFile_exists: true
                          tier: "free"
                          devices: {
                            devCode_in: [$product]
                          }
                          hatchId_gt: 0
                          hidden: false
                        }
                        order: [
                          hatchId_ASC
                        ]
                      ) {
                        total
                        limit
                        items {
                          title
                          id: hatchId
                          wavFile {
                            url
                          }
                        }
                      }
                    }
                """,
                product=device["product"]
            )
            sounds =  [{**s, "wavUrl": s['wavFile']['url']} for s in content["soundCollection"]["items"] if s['id'] != NO_SOUND_ID]
        else:
            sounds = []
        _LOGGER.debug(f"Sounds for {mac}: {sounds}")
        mac_to_sounds[mac] = sounds
    return mac_to_sounds
