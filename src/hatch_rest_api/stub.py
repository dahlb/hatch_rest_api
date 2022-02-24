# run with "python3 src/hatch_rest_api/us_kia_stub.py"
import logging
import asyncio
from awscrt import auth, io, mqtt, http
from awsiot.mqtt_connection_builder import websockets_with_default_aws_signing
from awsiot.iotshadow import IotShadowClient
from threading import Event

from getpass import getpass
from pathlib import Path
import sys

path_root = Path(__file__).parents[2]
sys.path.append(str(path_root))
from src.hatch_rest_api.hatch import Hatch
from src.hatch_rest_api.aws_http import AwsHttp
from src.hatch_rest_api.rest_mini import RestMini
from src.hatch_rest_api.const import RestMiniAudioTrack


logger = logging.getLogger("src.hatch_rest_api")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)


async def testing():
    api: Hatch = Hatch()
    email = input("Email: ")
    password = getpass()
    try:
        token = await api.login(email=email, password=password)
        member = await api.member(auth_token=token)
        iot_devices = await api.iot_devices(auth_token=token)
        device_name = iot_devices[0]["name"]
        product = iot_devices[0]["product"]
        thing_name = iot_devices[0]["thingName"]
        aws_token = await api.token(auth_token=token)
        logger.debug(aws_token)
        aws_http: AwsHttp = AwsHttp(api.api_session)
        aws_credentials = await aws_http.aws_credentials(
            region=aws_token["region"],
            identityId=aws_token["identityId"],
            aws_token=aws_token["token"],
        )
        logger.debug(aws_credentials["Credentials"])
        credentials_provider = auth.AwsCredentialsProvider.new_static(
            aws_credentials["Credentials"]["AccessKeyId"],
            aws_credentials["Credentials"]["SecretKey"],
            session_token=aws_credentials["Credentials"]["SessionToken"],
        )
        event_loop_group = io.EventLoopGroup(1)
        host_resolver = io.DefaultHostResolver(event_loop_group)
        client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)
        endpoint = aws_token["endpoint"].lstrip("https://")
        print(endpoint)
        mqtt_connection = websockets_with_default_aws_signing(
            region="us-west-2",
            credentials_provider=credentials_provider,
            clean_session=True,
            keep_alive_secs=30,
            client_bootstrap=client_bootstrap,
            endpoint=endpoint,
            client_id="hatch_rest_api",
        )

        try:
            connected_future = mqtt_connection.connect()
            connected_future.result()
            print("Connected!")

            shadow_client = IotShadowClient(mqtt_connection)
            print(device_name)
            rest_mini = RestMini(
                device_name=device_name,
                thing_name=thing_name,
                shadow_client=shadow_client,
            )

            def output():
                print(rest_mini)

            rest_mini.register_callback(output)
            #        print(rest_mini.shadow_value)

            # vehicles = await api.get_vehicles(session_id=session_id)
            # identifier = vehicles["vehicleSummary"][0]["vehicleIdentifier"]
            # key = vehicles["vehicleSummary"][0]["vehicleKey"]
            # await api.get_cached_vehicle_status(session_id=session_id, vehicle_key=key)
            # await api.lock(session_id=session_id, vehicle_key=key)
            #            rest_mini.set_audio_track(RestMiniAudioTrack.Ocean)
            #            rest_mini.set_volume(8)
            rest_mini.set_audio_track(RestMiniAudioTrack.NONE)
            Event().wait()
        finally:
            mqtt_connection.disconnect().result()
            raise
    finally:
        await api.cleanup_client_session()


asyncio.run(testing())
