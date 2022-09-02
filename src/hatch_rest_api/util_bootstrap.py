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
    mqtt_connection.connect().result()
    _LOGGER.debug(f"mqtt connection connected")

    shadow_client = IotShadowClient(mqtt_connection)

    def create_rest_devices(iot_device):
        if iot_device["product"] == "restPlus":
            return RestPlus(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                shadow_client=shadow_client,
            )
        else:
            return RestMini(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                shadow_client=shadow_client,
            )

    rest_devices = map(create_rest_devices, iot_devices)
    return (
        api,
        mqtt_connection,
        list(rest_devices),
        aws_credentials["Credentials"]["Expiration"],
    )
