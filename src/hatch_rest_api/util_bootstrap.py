"""Discover a Hatch account's devices and connect them to AWS IoT."""

import asyncio
from collections.abc import Callable
from functools import partial
import logging
from re import IGNORECASE, search, sub
from typing import Any
from uuid import uuid4

from aiohttp import ClientError, ClientSession
from awscrt import io, mqtt
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
from .restore import Restore, fetch_restore_alarms
from .restore_iot import RestoreIot
from .restore_v4 import RestoreV4
from .restore_v5 import RestoreV5
from .scheduled_routine import (
    ALARM_ROUTINE_TYPE,
    SCHEDULED_ROUTINE_ALARM_PRODUCTS,
    ScheduledRoutineAlarm,
    ScheduledRoutineAlarmMixin,
)
from .types import SimpleSoundContent, SoundContent

_LOGGER = logging.getLogger(__name__)

RestDevice = RestMini | RestPlus | RestIot | RestBaby | Restore | RestoreIot | RestoreV4 | RestoreV5

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


def _get_client_bootstrap() -> io.ClientBootstrap:
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


async def _connect_mqtt(loop: asyncio.AbstractEventLoop, mqtt_connection: mqtt.Connection) -> None:
    connect_future = await loop.run_in_executor(None, mqtt_connection.connect)
    await loop.run_in_executor(None, partial(connect_future.result, MQTT_CONNECT_TIMEOUT))


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
        import _awscrt  # noqa: PLC0415
    except ImportError:
        return False
    binding = getattr(_awscrt, _NATIVE_CONNECT, None)
    if binding is None or getattr(binding, _RECONCILED_FLAG, False):
        return False

    def reconciled_connect(*args: Any) -> Any:
        if len(args) > expected:
            args = args[:expected]
        elif len(args) < expected:
            args = args + (None,) * (expected - len(args))
        return binding(*args)

    setattr(reconciled_connect, _RECONCILED_FLAG, True)
    setattr(_awscrt, _NATIVE_CONNECT, reconciled_connect)
    _LOGGER.warning(
        "awscrt passed %s arguments to a native connect binding that takes %s, so its "
        "modules are not all from the same version. Reconciling the call and retrying; "
        "restart to load a consistent awscrt.",
        given,
        expected,
    )
    return True


async def get_rest_devices(
    email: str,
    password: str,
    client_session: ClientSession | None = None,
    on_connection_interrupted: Callable[..., None] | None = None,
    on_connection_resumed: Callable[..., None] | None = None,
) -> tuple[Hatch, mqtt.Connection, list[RestDevice], Any]:
    """Log in, discover the account's devices and connect them over AWS IoT.

    Args:
        email: Hatch account email.
        password: Hatch account password.
        client_session: Optional aiohttp session to reuse for HTTP requests.
        on_connection_interrupted: Callback passed to the MQTT connection.
        on_connection_resumed: Callback passed to the MQTT connection.

    Returns:
        The API client, the MQTT connection, one object per supported device, and the
        expiration of the AWS credentials, after which the connection must be rebuilt.

    Raises:
        BaseError: If the account has no compatible devices.
    """
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
    alarms_map = await _get_alarms_for_all_scheduled_routine_devices(api, token, iot_devices)
    restore_routines_map = await _probe_routines_for_restore_devices(api, token, iot_devices)
    restore_alarms_map = await _fetch_alarms_for_restore_devices(api, token, iot_devices)
    sounds_map = await _get_sound_content_for_all_v2_devices(api, token, contentful, iot_devices)
    aws_http: AwsHttp = AwsHttp(api.api_session)
    aws_credentials = await aws_http.aws_credentials(
        region=aws_token["region"],
        identityId=aws_token["identityId"],
        aws_token=aws_token["token"],
    )
    _LOGGER.debug("AWS credentials: %s", aws_credentials)
    credentials_provider = AwsCredentialsProvider.new_static(
        aws_credentials["Credentials"]["AccessKeyId"],
        aws_credentials["Credentials"]["SecretKey"],
        session_token=aws_credentials["Credentials"]["SessionToken"],
    )
    client_bootstrap = _get_client_bootstrap()
    endpoint = aws_token["endpoint"].removeprefix("https://")
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
            client_id=f"hatch_rest_api/{safe_email}/{uuid4()!s}",
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
        _LOGGER.error("MQTT connection failed with exception %s", e)
        raise

    shadow_client = IotShadowClient(mqtt_connection)

    def _with_alarm_api(
        rest_device: RestDevice, alarms: list[ScheduledRoutineAlarm] | None
    ) -> RestDevice:
        if isinstance(rest_device, ScheduledRoutineAlarmMixin):
            rest_device.configure_alarm_api(api=api, auth_token=token, alarms=alarms)
        return rest_device

    def create_rest_devices(iot_device: dict[str, Any]) -> RestDevice:
        mac_address = iot_device["macAddress"]
        if mac_address in favorites_map:
            favorites = list(favorites_map[mac_address])
        else:
            _LOGGER.debug("Iot device %s has no favorites", iot_device)
            favorites = []
        if mac_address in routines_map:
            routines = list(routines_map[mac_address])
        else:
            _LOGGER.debug("Iot device %s has no routines", iot_device)
            routines = []
        if mac_address in alarms_map:
            alarms = alarms_map[mac_address]
        else:
            _LOGGER.debug("Iot device %s has no alarms", iot_device)
            alarms = []
        if iot_device["product"] == "restPlus":
            return RestPlus(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                mac=mac_address,
                shadow_client=shadow_client,
            )
        if iot_device["product"] in ["riot", "riotPlus"]:
            return RestIot(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                mac=mac_address,
                shadow_client=shadow_client,
                favorites=favorites,
                sounds=sounds_map[mac_address],
            )
        if iot_device["product"] == "restore":
            # Must stay explicit: an unmatched product falls through to
            # RestMini below, which reads a shadow this model does not have.
            restore = Restore(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                mac=mac_address,
                shadow_client=shadow_client,
                routines=restore_routines_map.get(mac_address),
            )
            restore_alarms, alarm_api_url = restore_alarms_map.get(mac_address) or (None, None)
            # Configured even when the first fetch failed, so the periodic
            # alarm refresh can try again.
            restore.configure_alarm_api(
                api=api, auth_token=token, alarms=restore_alarms, api_url=alarm_api_url
            )
            return restore
        if iot_device["product"] == "restoreIot":
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
        if iot_device["product"] == "restoreV4":
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
        if iot_device["product"] == "restoreV5":
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
        if iot_device["product"] == "restBaby":
            return RestBaby(
                device_name=iot_device["name"],
                thing_name=iot_device["thingName"],
                mac=mac_address,
                shadow_client=shadow_client,
                favorites=routines + favorites,
                sounds=sounds_map[mac_address],
            )
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


async def _get_favorites_for_all_v2_devices(
    api: Hatch, token: str, iot_devices: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    mac_to_favorite = {}
    for device in iot_devices:
        if device["product"] in [
            "riot",
            "riotPlus",
            "restBaby",
            "restoreV4",
            "restoreV5",
        ]:
            mac = device["macAddress"]
            favorites = await api.favorites(auth_token=token, mac=mac)
            _LOGGER.debug("Favorites for %s: %s", mac, favorites)
            mac_to_favorite[mac] = favorites
    return mac_to_favorite


async def _get_routines_for_all_v2_devices(
    api: Hatch, token: str, iot_devices: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    mac_to_routines = {}
    for device in iot_devices:
        if device["product"] in [
            "riot",
            "restBaby",
            "restoreIot",
            "restoreV4",
            "restoreV5",
        ]:
            mac = device["macAddress"]
            routines = await api.routines(auth_token=token, mac=mac)
            _LOGGER.debug("Routines for %s: %s", mac, routines)
            mac_to_routines[mac] = routines
    return mac_to_routines


async def _probe_routines_for_restore_devices(
    api: Hatch, token: str, iot_devices: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]] | None]:
    """Fetch original Restores' routines, without letting a failure count.

    Unlike the helpers for the other models, a failure here, rate limiting
    included, is logged and skipped instead of failing setup.

    Args:
        api: Logged-in Hatch API client.
        token: Hatch auth token.
        iot_devices: The account's devices.

    Returns:
        The routines by MAC address, or None for a device whose fetch failed.
    """
    mac_to_routines: dict[str, list[dict[str, Any]] | None] = {}
    for device in iot_devices:
        if device["product"] != "restore":
            continue
        mac = device["macAddress"]
        try:
            routines: list[dict[str, Any]] | None = await api.routines(auth_token=token, mac=mac)
        except (ClientError, KeyError, TypeError, AttributeError) as e:
            # ClientError covers RateError and AuthError; the others come from
            # an unexpected payload shape.
            _LOGGER.debug("Could not fetch routines for restore %s: %r", mac, e)
            routines = None
        _LOGGER.debug("Routines for restore %s: %s", mac, routines)
        mac_to_routines[mac] = routines
    return mac_to_routines


async def _fetch_alarms_for_restore_devices(
    api: Hatch, token: str, iot_devices: list[dict[str, Any]]
) -> dict[str, tuple[list[dict[str, Any]], str] | None]:
    """Fetch original Restores' alarms; a failure is logged, not raised.

    Args:
        api: Logged-in Hatch API client.
        token: Hatch auth token.
        iot_devices: The account's devices.

    Returns:
        By MAC address: the alarms and the alarm API host that served them, or
        None when the fetch failed, in which case the device comes up without
        alarms.
    """
    mac_to_alarms: dict[str, tuple[list[dict[str, Any]], str] | None] = {}
    for device in iot_devices:
        if device["product"] != "restore":
            continue
        mac = device["macAddress"]
        try:
            mac_to_alarms[mac] = await fetch_restore_alarms(api, token, mac)
        except (ClientError, KeyError, TypeError, ValueError) as e:
            _LOGGER.debug("Could not fetch alarms for restore %s: %r", mac, e)
            mac_to_alarms[mac] = None
        _LOGGER.debug("Alarms for restore %s: %s", mac, mac_to_alarms[mac])
    return mac_to_alarms


async def _get_alarms_for_all_scheduled_routine_devices(
    api: Hatch, token: str, iot_devices: list[dict[str, Any]]
) -> dict[str, list[ScheduledRoutineAlarm] | None]:
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
                _LOGGER.warning("Could not fetch alarm routines for %s: %s", mac, e)
                alarms = None
            _LOGGER.debug("Alarms for %s: %s", mac, alarms)
            mac_to_alarms[mac] = alarms
    return mac_to_alarms


async def _get_sound_content_for_all_v2_devices(
    api: Hatch, token: str, contentful: Contentful, iot_devices: list[dict[str, Any]]
) -> dict[str, list[SoundContent | SimpleSoundContent]]:
    mac_to_sounds = {}
    for device in iot_devices:
        mac = device["macAddress"]
        if device["product"] in ["riot", "riotPlus", "restBaby"]:
            try:
                content = await api.content(auth_token=token, product="riot", content=["sound"])
                sounds = [s for s in content["contentItems"] if s["id"] != NO_SOUND_ID]
            except RateError as e:
                _LOGGER.warning("Rate limit error when fetching sounds for %s: %s", mac, e)
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
                _LOGGER.warning("Rate limit error when fetching sounds for %s: %s", mac, e)
                sounds = []
        else:
            sounds = []
        _LOGGER.debug("Sounds for %s: %s", mac, sounds)
        mac_to_sounds[mac] = sounds
    return mac_to_sounds
