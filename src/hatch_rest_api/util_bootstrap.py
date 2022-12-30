import logging

from awscrt import io
from awscrt.auth import AwsCredentialsProvider
from awsiot.mqtt_connection_builder import websockets_with_default_aws_signing
from awsiot.iotshadow import IotShadowClient
from aiohttp import ClientSession

from .hatch import Hatch
from .aws_http import AwsHttp
from .rest_mini import RestMini
from .rest_plus import RestPlus
from .riot import RestIot

_LOGGER = logging.getLogger(__name__)


async def get_rest_devices(
    email: str,
    password: str,
    client_session: ClientSession = None,
    on_connection_interrupted=None,
    on_connection_resumed=None,
):
    if _LOGGER.isEnabledFor(logging.DEBUG):
        io.init_logging(io.LogLevel.Debug, "hatch_rest_api-aws_mqtt.log")
    api = Hatch(client_session=client_session)
    token = await api.login(email=email, password=password)
    iot_devices = await api.iot_devices(auth_token=token)
    aws_token = await api.token(auth_token=token)
    favorites_map = await _get_favorites_for_all_v2_devices(api, token, iot_devices)
    # This call will fetch sounds for a v2 device but the official app doesn't appear to use these sounds
    # sounds = await _get_sound_content_for_v2_devices(api, token, iot_devices)
    aws_http: AwsHttp = AwsHttp(api.api_session)
    aws_credentials = await aws_http.aws_credentials(
        region=aws_token["region"],
        identityId=aws_token["identityId"],
        aws_token=aws_token["token"],
    )
    credentials_provider = AwsCredentialsProvider.new_static(
        aws_credentials["Credentials"]["AccessKeyId"],
        aws_credentials["Credentials"]["SecretKey"],
        session_token=aws_credentials["Credentials"]["SessionToken"],
    )
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)
    endpoint = aws_token["endpoint"].lstrip("https://")
    mqtt_connection = websockets_with_default_aws_signing(
        region="us-west-2",
        credentials_provider=credentials_provider,
        keep_alive_secs=30,
        client_bootstrap=client_bootstrap,
        endpoint=endpoint,
        client_id=f"hatch_rest_api/{email}",
        on_connection_interrupted=on_connection_interrupted,
        on_connection_resumed=on_connection_resumed,
    )
    try:
        mqtt_connection.connect().result()
        _LOGGER.debug(f"mqtt connection connected")
    except Exception as e:
        _LOGGER.error('MQTT connection failed with exception {}'.format(e))
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
    mac_to_fav = {}
    for device in iot_devices:
        if device["product"] in ["riot", "riotPlus"]:
            mac = device["macAddress"]
            favorites = await api.favorites(auth_token=token, mac=mac)
            _LOGGER.debug(f"Favorites for {mac}: {favorites}")
            mac_to_fav[mac] = favorites
    return mac_to_fav


async def _get_sound_content_for_v2_devices(api, token, iot_devices):
    sounds = []
    for device in iot_devices:
        if device["product"] in ["riot", "riotPlus"] and not sounds:
            content = await api.content(
                auth_token=token, product="riot", content=["sound"]
            )
            sounds = content["contentItems"]
            _LOGGER.debug(f"Sounds: {sounds}")
    return sounds
