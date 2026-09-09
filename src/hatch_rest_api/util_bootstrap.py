import asyncio
import logging
from functools import partial
from re import IGNORECASE, search, sub
from uuid import uuid4

from aiohttp import ClientError, ClientSession
from awscrt import io
from awscrt.auth import AwsCredentialsProvider
from awsiot.iotshadow import IotShadowClient
from awsiot.mqtt_connection_builder import websockets_with_default_aws_signing

from . import BaseError
from .aws_http import AwsHttp
from .const import NO_SOUND_ID
from .contentful import Contentful
from .errors import RateError
from .hatch import Hatch
from .rest_baby import RestBaby
from .rest_iot import RestIot
from .rest_mini import RestMini
from .rest_plus import RestPlus
from .restore_iot import RestoreIot
from .restore_v4 import RestoreV4
from .restore_v5 import RestoreV5
from .scheduled_routine import (
    ALARM_ROUTINE_TYPE,
    SCHEDULED_ROUTINE_ALARM_PRODUCTS,
    ScheduledRoutineAlarmMixin,
)
from .types import SimpleSoundContent

_LOGGER = logging.getLogger(__name__)

# Seconds to wait for the MQTT connection to establish before giving up.
# Prevents thread pool workers from blocking indefinitely when the Hatch
# cloud is unreachable in ways that don't fail fast (e.g. hung TCP).
MQTT_CONNECT_TIMEOUT = 30

# awscrt raises this when its python wrapper and its native extension
# disagree about the argument list of the MQTT connect binding, e.g.
#     TypeError: function takes exactly 17 arguments (18 given)
_NATIVE_ARITY_ERROR = r"takes exactly (\d+) arguments? \((\d+) given\)"
_NATIVE_CONNECT = "mqtt_client_connection_connect"
_RECONCILED_FLAG = "_hatch_rest_api_reconciled"

io.init_logging(io.LogLevel.NoLogs, "stderr")


def _get_client_bootstrap():
    """Return the process-wide ClientBootstrap used for every MQTT connection.

    awscrt starts a native event loop thread per EventLoopGroup and only stops
    it when the native resource is destroyed. Nothing here ever destroys one:
    the shadow subscriptions set up per device hold callbacks that reference
    the device, which references the connection, which owns the bootstrap, so
    the whole graph stays reachable even after ``disconnect()``. Building a
    group per call therefore stranded a thread, its pipe pair and its CRT
    buffers every time.

    Callers rebuild the connection whenever the AWS credentials expire, which
    Hatch issues hourly, so that cost accumulated for as long as the process
    ran. Sharing awscrt's static default keeps it flat at one thread.
    """
    return io.ClientBootstrap.get_or_create_static_default()


async def _connect_mqtt(loop, mqtt_connection):
    connect_future = await loop.run_in_executor(None, mqtt_connection.connect)
    await loop.run_in_executor(
        None, partial(connect_future.result, MQTT_CONNECT_TIMEOUT)
    )


def _reconcile_awscrt_arity(error: TypeError) -> bool:
    """Bridge an argument count gap between awscrt's wrapper and extension.

    awsiotsdk pins an exact awscrt, so installing it can replace awscrt on disk
    while the interpreter is already running. ``awscrt/__init__.py`` -- and the
    ``_awscrt`` extension it has already loaded -- then stay resident from the
    old version, while ``awscrt/mqtt.py`` is imported afterwards from the new
    one. The newer wrapper passes the trailing IoT metrics argument, added in
    awscrt 0.32.1, to a native binding that predates it::

        TypeError: function takes exactly 17 arguments (18 given)

    Restarting the process realigns the two halves, but until then every
    connection attempt fails the same way, so wrap the native binding to
    trim or pad the trailing argument to whatever the resident extension takes.

    Only a one argument gap is bridged. That is the drift being reconciled, and
    a wider one would mean handing the binding values meant for other
    parameters. Returns whether anything was patched, so the caller only
    retries when there is something new to try.
    """
    match = search(_NATIVE_ARITY_ERROR, str(error))
    if match is None:
        return False
    expected, given = int(match.group(1)), int(match.group(2))
    if abs(expected - given) != 1:
        return False
    # Imported here so the dependency on awscrt's private extension module is
    # confined to this recovery path.
    try:
        import _awscrt
    except ImportError:
        return False
    binding = getattr(_awscrt, _NATIVE_CONNECT, None)
    if binding is None or getattr(binding, _RECONCILED_FLAG, False):
        return False

    def reconciled_connect(*args):
        if len(args) > expected:
            args = args[:expected]
        elif len(args) < expected:
            args = args + (None,) * (expected - len(args))
        return binding(*args)

    setattr(reconciled_connect, _RECONCILED_FLAG, True)
    setattr(_awscrt, _NATIVE_CONNECT, reconciled_connect)
    _LOGGER.warning(
        f"awscrt passed {given} arguments to a native connect binding that "
        f"takes {expected}, so its modules are not all from the same version. "
        "Reconciling the call and retrying; restart to load a consistent awscrt."
    )
    return True


async def get_rest_devices(
    email: str,
    password: str,
    client_session: ClientSession = None,
    on_connection_interrupted=None,
    on_connection_resumed=None,
):
    loop = asyncio.get_running_loop()
    aws_log_level = io.LogLevel.Debug if _LOGGER.isEnabledFor(logging.DEBUG) else io.LogLevel.NoLogs
    await loop.run_in_executor(None, io.set_log_level, aws_log_level)
    api = Hatch(client_session=client_session)
    contentful = Contentful(client_session=client_session)
    token = await api.login(email=email, password=password)
    iot_devices = await api.iot_devices(auth_token=token)
    if len(iot_devices) == 0:
        raise BaseError("No compatible devices found on this hatch account")
    aws_token = await api.token(auth_token=token)
    favorites_map = await _get_favorites_for_all_v2_devices(api, token, iot_devices)
    routines_map = await _get_routines_for_all_v2_devices(api, token, iot_devices)
    alarms_map = await _get_alarms_for_all_scheduled_routine_devices(
        api, token, iot_devices
    )
    sounds_map = await _get_sound_content_for_all_v2_devices(
        api, token, contentful, iot_devices
    )
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
    client_bootstrap = _get_client_bootstrap()
    endpoint = aws_token["endpoint"].lstrip("https://")
    safe_email = sub("[^a-z]", "", email, flags=IGNORECASE).lower()
    mqtt_connection = await loop.run_in_executor(
        None,
        partial(
            websockets_with_default_aws_signing,
            region=aws_token["region"],
            credentials_provider=credentials_provider,
            keep_alive_secs=30,
            client_bootstrap=client_bootstrap,
            endpoint=endpoint,
            client_id=f"hatch_rest_api/{safe_email}/{str(uuid4())}",
            on_connection_interrupted=on_connection_interrupted,
            on_connection_resumed=on_connection_resumed,
            # Opt out of the AWS IoT SDK metrics that awsiot otherwise appends
            # to the CONNECT packet username. They report AWS SDK/platform
            # details to AWS and are of no use to us, but building them makes
            # awscrt introspect private ClientTlsContext internals
            # (tls_ctx._certificate_source). On installs where awscrt's modules
            # are not all from the same version, that attribute is missing and
            # the connection blows up before it is ever attempted:
            #     AttributeError: 'ClientTlsContext' object
            #     has no attribute '_certificate_source'
            # Disabling metrics skips that code path entirely.
            enable_metrics_collection=False,
        ),
    )
    try:
        try:
            await _connect_mqtt(loop, mqtt_connection)
        except TypeError as e:
            if not _reconcile_awscrt_arity(e):
                raise
            await _connect_mqtt(loop, mqtt_connection)
        _LOGGER.debug("mqtt connection connected")
    except Exception as e:
        _LOGGER.error(f"MQTT connection failed with exception {e}")
        raise e

    shadow_client = IotShadowClient(mqtt_connection)

    def _with_alarm_api(rest_device, alarms):
        if isinstance(rest_device, ScheduledRoutineAlarmMixin):
            rest_device.configure_alarm_api(api=api, auth_token=token, alarms=alarms)
        return rest_device

    def create_rest_devices(iot_device):
        mac_address = iot_device["macAddress"]
        if mac_address in favorites_map:
            favorites = list(favorites_map[mac_address])
        else:
            _LOGGER.debug(f"Iot device {iot_device} has no favorites")
            favorites = []
        if mac_address in routines_map:
            routines = list(routines_map[mac_address])
        else:
            _LOGGER.debug(f"Iot device {iot_device} has no routines")
            routines = []
        if mac_address in alarms_map:
            alarms = alarms_map[mac_address]
        else:
            _LOGGER.debug(f"Iot device {iot_device} has no alarms")
            alarms = []
        if iot_device["product"] == "restPlus":
            return RestPlus(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                mac=mac_address,
                shadow_client=shadow_client,
            )
        elif iot_device["product"] in ["riot", "riotPlus"]:
            return RestIot(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                mac=mac_address,
                shadow_client=shadow_client,
                favorites=favorites,
                sounds=sounds_map[mac_address],
            )
        elif iot_device["product"] == "restoreIot":
            return _with_alarm_api(
                RestoreIot(
                    device_name=iot_device["name"],
                    thing_name=iot_device["thingName"],
                    mac=mac_address,
                    shadow_client=shadow_client,
                    favorites=routines + favorites,
                    sounds=sounds_map[mac_address],
                ),
                alarms,
            )
        elif iot_device["product"] == "restoreV4":
            return _with_alarm_api(
                RestoreV4(
                    device_name=iot_device["name"],
                    thing_name=iot_device["thingName"],
                    mac=mac_address,
                    shadow_client=shadow_client,
                    favorites=routines + favorites,
                    sounds=sounds_map[mac_address],
                ),
                alarms,
            )
        elif iot_device["product"] == "restoreV5":
            return _with_alarm_api(
                RestoreV5(
                    device_name=iot_device["name"],
                    thing_name=iot_device["thingName"],
                    mac=mac_address,
                    shadow_client=shadow_client,
                    favorites=routines + favorites,
                    sounds=sounds_map[mac_address],
                ),
                alarms,
            )
        elif iot_device["product"] == "restBaby":
            return RestBaby(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                mac=mac_address,
                shadow_client=shadow_client,
                favorites=routines + favorites,
                sounds=sounds_map[mac_address],
            )
        else:
            return RestMini(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                mac=mac_address,
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
        if device["product"] in ["riot", "riotPlus", "restBaby", "restoreV4", "restoreV5"]:
            mac = device["macAddress"]
            favorites = await api.favorites(auth_token=token, mac=mac)
            _LOGGER.debug(f"Favorites for {mac}: {favorites}")
            mac_to_favorite[mac] = favorites
    return mac_to_favorite


async def _get_routines_for_all_v2_devices(api, token, iot_devices):
    mac_to_routines = {}
    for device in iot_devices:
        if device["product"] in ["riot", "restBaby", "restoreIot", "restoreV4", "restoreV5"]:
            mac = device["macAddress"]
            routines = await api.routines(auth_token=token, mac=mac)
            _LOGGER.debug(f"Routines for {mac}: {routines}")
            mac_to_routines[mac] = routines
    return mac_to_routines


async def _get_alarms_for_all_scheduled_routine_devices(api, token, iot_devices):
    mac_to_alarms = {}
    for device in iot_devices:
        if device["product"] in SCHEDULED_ROUTINE_ALARM_PRODUCTS:
            mac = device["macAddress"]
            try:
                alarms = await api.scheduled_routines(
                    auth_token=token,
                    mac=mac,
                    types=[ALARM_ROUTINE_TYPE],
                )
            except RateError:
                raise
            except ClientError as e:
                _LOGGER.warning(
                    f"Could not fetch alarm routines for {mac}: {str(e)}"
                )
                alarms = None
            _LOGGER.debug(f"Alarms for {mac}: {alarms}")
            mac_to_alarms[mac] = alarms
    return mac_to_alarms


async def _get_sound_content_for_all_v2_devices(
    api: Hatch, token: str, contentful: Contentful, iot_devices
) -> dict[str, list[SimpleSoundContent]]:
    mac_to_sounds = {}
    for device in iot_devices:
        mac = device["macAddress"]
        if device["product"] in ["riot", "riotPlus", "restBaby"]:
            try:
                content = await api.content(
                    auth_token=token, product="riot", content=["sound"]
                )
                sounds = [s for s in content["contentItems"] if s["id"] != NO_SOUND_ID]
            except RateError as e:
                _LOGGER.warning(
                    f"Rate limit error when fetching sounds for {mac}: {str(e)}"
                )
                sounds = []
        elif device["product"] in ["restoreV4", "restoreV5"]:
            try:
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
                    product=device["product"],
                )
                sounds = [
                    {**s, "wavUrl": s["wavFile"]["url"]}
                    for s in content["soundCollection"]["items"]
                    if s["id"] != NO_SOUND_ID
                ]
            except RateError as e:
                _LOGGER.warning(
                    f"Rate limit error when fetching sounds for {mac}: {str(e)}"
                )
                sounds = []
        else:
            sounds = []
        _LOGGER.debug(f"Sounds for {mac}: {sounds}")
        mac_to_sounds[mac] = sounds
    return mac_to_sounds
