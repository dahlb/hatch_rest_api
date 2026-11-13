import asyncio
import sys
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from aiohttp import ClientError

from hatch_rest_api import RateError, RestMini, Restore, util_bootstrap


class FakeHatch:
    """Stands in for the Hatch REST client, returning canned payloads."""

    def __init__(self, *args, **kwargs):
        self.api_session = MagicMock()

    async def login(self, **kwargs):
        return "auth-token"

    async def iot_devices(self, **kwargs):
        return [
            {
                "product": "restMini",
                "name": "Nursery",
                "thingName": "thing-1",
                "macAddress": "AA:BB:CC:DD:EE:FF",
            }
        ]

    async def token(self, **kwargs):
        return {
            "region": "us-east-1",
            "identityId": "identity-1",
            "token": "aws-token",
            "endpoint": "https://example-ats.iot.us-east-1.amazonaws.com",
        }


class FakeAwsHttp:
    def __init__(self, *args, **kwargs):
        pass

    async def aws_credentials(self, **kwargs):
        return {
            "Credentials": {
                "AccessKeyId": "key",
                "SecretKey": "secret",
                "SessionToken": "session",
                "Expiration": 1780000000,
            }
        }


class FakeShadowClient:
    """IotShadowClient stub.

    subscribe_* returns the (future, topic) pair the real client returns;
    publish_* returns a future whose .result() is a MagicMock.
    """

    def __getattr__(self, name):
        if name.startswith("subscribe_"):
            return lambda *args, **kwargs: (MagicMock(), MagicMock())
        return lambda *args, **kwargs: MagicMock()


class FlakyMqttConnection:
    """MQTT connection whose first ``connect`` futures raise ``error``.

    awscrt's ``connect`` never raises inline; it hands the exception to the
    future it returns, so the failure surfaces from ``future.result()``.
    """

    def __init__(self, error, failures=1):
        self.error = error
        self.remaining_failures = failures
        self.connect_calls = 0

    def connect(self):
        self.connect_calls += 1
        future = MagicMock()
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            future.result.side_effect = self.error
        return future


class FakeNativeBinding:
    """Stand-in for ``_awscrt.mqtt_client_connection_connect``.

    Accepts exactly ``arity`` positional arguments and reports anything else
    the way the native extension does.
    """

    def __init__(self, arity):
        self.arity = arity
        self.calls = []

    def __call__(self, *args):
        if len(args) != self.arity:
            raise TypeError(
                f"function takes exactly {self.arity} arguments "
                f"({len(args)} given)"
            )
        self.calls.append(args)


def _run_bootstrap(io_mock=None, connection=None):
    """Run get_rest_devices with every network dependency faked.

    Returns the patched connection builder and the patched awscrt ``io`` module
    so tests can assert on how each was used. Pass an ``io_mock`` to share one
    across several runs, which is how a reconnect is simulated, or a
    ``connection`` to control what the builder hands back.
    """
    builder = MagicMock(return_value=MagicMock() if connection is None else connection)
    if io_mock is None:
        io_mock = MagicMock()

    with _patched_bootstrap(FakeHatch, io_mock, builder):
        asyncio.run(
            util_bootstrap.get_rest_devices(
                email="user@example.com", password="hunter2"
            )
        )

    return builder, io_mock


def _patched_bootstrap(hatch, io_mock, builder) -> ExitStack:
    """Patch every network dependency of get_rest_devices.

    ``hatch`` replaces the Hatch REST client class; anything callable that
    returns a client will do, so tests can hand in a prepared instance.
    """
    stack = ExitStack()
    for name, replacement in (
        ("Hatch", hatch),
        ("Contentful", MagicMock()),
        ("AwsHttp", FakeAwsHttp),
        ("AwsCredentialsProvider", MagicMock()),
        ("io", io_mock),
        ("IotShadowClient", lambda *a, **kw: FakeShadowClient()),
        ("websockets_with_default_aws_signing", builder),
    ):
        stack.enter_context(patch.object(util_bootstrap, name, replacement))
    return stack


def _bootstrap_devices(api):
    """Run get_rest_devices against the prepared client ``api``; return its devices."""
    with _patched_bootstrap(lambda *a, **kw: api, MagicMock(), MagicMock()):
        _, _, devices, _ = asyncio.run(
            util_bootstrap.get_rest_devices(
                email="user@example.com", password="hunter2"
            )
        )
    return devices


class RestoreHatch(FakeHatch):
    """A Hatch account holding one original Restore and one Rest Mini."""

    def __init__(self, routines=None, routines_error=None, alarms=None):
        super().__init__()
        self._routines = routines
        self._routines_error = routines_error
        self._alarms = alarms
        self.routines_calls = []
        self.alarm_calls = []

    async def iot_devices(self, **kwargs):
        return [
            {
                "product": "restore",
                "name": "Bedroom",
                "thingName": "thing-restore",
                "macAddress": "11:22:33:44:55:66",
            },
            *await super().iot_devices(**kwargs),
        ]

    async def routines(self, auth_token, mac):
        self.routines_calls.append(mac)
        if self._routines_error is not None:
            raise self._routines_error
        return self._routines

    async def restore_alarms(self, auth_token, mac, base_url):
        self.alarm_calls.append((mac, base_url))
        if self._alarms is None:
            raise ClientError("Invalid response format from API (status: 404)")
        return self._alarms


class GetRestDevicesClientBootstrapTest(unittest.TestCase):
    """Regression guard for the awscrt event loop thread leak.

    ``get_rest_devices`` used to build an EventLoopGroup, DefaultHostResolver
    and ClientBootstrap of its own on every call. awscrt starts a native thread
    per EventLoopGroup and only stops it once the native resource is destroyed,
    which never happened while the connection graph stayed reachable. Since
    callers reconnect every time the AWS credentials expire -- hourly -- each
    refresh stranded another thread, pipe pair and set of CRT buffers.
    """

    def test_uses_shared_static_bootstrap(self):
        _, io_mock = _run_bootstrap()

        io_mock.ClientBootstrap.get_or_create_static_default.assert_called_once()

    def test_does_not_build_per_connection_event_loop_group(self):
        _, io_mock = _run_bootstrap()

        io_mock.EventLoopGroup.assert_not_called()
        io_mock.DefaultHostResolver.assert_not_called()

    def test_reconnects_reuse_the_same_bootstrap(self):
        io_mock = MagicMock()
        builder_one, _ = _run_bootstrap(io_mock)
        builder_two, _ = _run_bootstrap(io_mock)

        self.assertIs(
            builder_one.call_args.kwargs["client_bootstrap"],
            builder_two.call_args.kwargs["client_bootstrap"],
        )
        io_mock.EventLoopGroup.assert_not_called()


class GetRestDevicesMetricsTest(unittest.TestCase):
    """Regression guard for dahlb/ha_hatch#323.

    awsiot defaults ``enable_metrics_collection`` to True, which makes awscrt
    build an AWS IoT SDK metrics string by reading private ClientTlsContext
    internals. On installs whose awscrt modules are not all the same version
    that read raises::

        AttributeError: 'ClientTlsContext' object has no attribute
        '_certificate_source'

    which fails setup before the MQTT connection is even attempted. We must
    keep passing enable_metrics_collection=False so that path is never entered.
    """

    def test_metrics_collection_disabled(self):
        builder, _ = _run_bootstrap()

        builder.assert_called_once()
        self.assertIs(builder.call_args.kwargs["enable_metrics_collection"], False)

    def test_devices_still_created(self):
        builder, _ = _run_bootstrap()

        # Sanity check that disabling metrics did not disturb the rest of the
        # bootstrap: the connection is still built and devices still returned.
        self.assertEqual(
            builder.call_args.kwargs["endpoint"],
            "example-ats.iot.us-east-1.amazonaws.com",
        )


class GetRestDevicesNativeArityTest(unittest.TestCase):
    """Regression guard for dahlb/ha_hatch#293.

    awsiotsdk pins an exact awscrt, so installing it can swap awscrt on disk
    under a running interpreter. The resident ``_awscrt`` extension then keeps
    the old connect signature while the freshly imported ``awscrt/mqtt.py``
    passes the trailing IoT metrics argument added in awscrt 0.32.1::

        TypeError: function takes exactly 17 arguments (18 given)

    Every connection attempt fails that way until the process restarts, so the
    bootstrap reconciles the two halves once and retries.
    """

    def _native(self, arity):
        binding = FakeNativeBinding(arity)
        return SimpleNamespace(mqtt_client_connection_connect=binding), binding

    def test_trims_the_argument_the_extension_does_not_take(self):
        native, binding = self._native(17)
        connection = FlakyMqttConnection(
            TypeError("function takes exactly 17 arguments (18 given)")
        )

        with patch.dict(sys.modules, {"_awscrt": native}):
            _run_bootstrap(connection=connection)
            native.mqtt_client_connection_connect(*range(18))

        self.assertEqual(connection.connect_calls, 2)
        self.assertEqual(binding.calls, [tuple(range(17))])

    def test_pads_the_argument_the_extension_expects(self):
        native, binding = self._native(18)
        connection = FlakyMqttConnection(
            TypeError("function takes exactly 18 arguments (17 given)")
        )

        with patch.dict(sys.modules, {"_awscrt": native}):
            _run_bootstrap(connection=connection)
            native.mqtt_client_connection_connect(*range(17))

        self.assertEqual(connection.connect_calls, 2)
        self.assertEqual(binding.calls, [tuple(range(17)) + (None,)])

    def test_leaves_unrelated_type_errors_alone(self):
        native, binding = self._native(17)
        connection = FlakyMqttConnection(
            TypeError("connect() got an unexpected keyword argument 'username'")
        )

        with (
            patch.dict(sys.modules, {"_awscrt": native}),
            self.assertRaises(TypeError),
        ):
            _run_bootstrap(connection=connection)

        self.assertEqual(connection.connect_calls, 1)
        self.assertIs(native.mqtt_client_connection_connect, binding)

    def test_leaves_gaps_wider_than_one_argument_alone(self):
        """Trimming a wider gap would feed the binding other parameters."""
        native, binding = self._native(15)
        connection = FlakyMqttConnection(
            TypeError("function takes exactly 15 arguments (18 given)")
        )

        with (
            patch.dict(sys.modules, {"_awscrt": native}),
            self.assertRaises(TypeError),
        ):
            _run_bootstrap(connection=connection)

        self.assertEqual(connection.connect_calls, 1)
        self.assertIs(native.mqtt_client_connection_connect, binding)

    def test_retries_only_once(self):
        native, _ = self._native(17)
        connection = FlakyMqttConnection(
            TypeError("function takes exactly 17 arguments (18 given)"),
            failures=2,
        )

        with (
            patch.dict(sys.modules, {"_awscrt": native}),
            self.assertRaises(TypeError),
        ):
            _run_bootstrap(connection=connection)

        self.assertEqual(connection.connect_calls, 2)


class GetRestDevicesRestoreTest(unittest.TestCase):
    """The original Restore (product ``restore``) must not become a RestMini.

    Any product create_rest_devices does not match falls through to RestMini,
    whose shadow parser reads keys this model does not report.
    """

    def test_builds_a_restore(self):
        restore, rest_mini = _bootstrap_devices(RestoreHatch(routines=[]))

        self.assertIsInstance(restore, Restore)
        self.assertEqual(restore.device_name, "Bedroom")
        self.assertEqual(restore.thing_name, "thing-restore")
        self.assertEqual(restore.mac, "11:22:33:44:55:66")
        self.assertIsInstance(rest_mini, RestMini)

    def test_probes_routines_for_the_restore_only(self):
        routines = [{"id": 7, "name": "Bedtime", "type": "routine"}]
        api = RestoreHatch(routines=routines)

        restore, _ = _bootstrap_devices(api)

        self.assertEqual(api.routines_calls, ["11:22:33:44:55:66"])
        self.assertEqual(restore.routines, routines)
        # Not treated as favorites: those become scenes that call set_favorite.
        self.assertEqual(restore.favorites, [])

    def test_a_failed_routine_probe_does_not_fail_setup(self):
        for error in (
            ClientError("api error:not supported"),
            RateError("API rate limit exceeded."),
            KeyError("payload"),
        ):
            with self.subTest(error=type(error).__name__):
                restore, _ = _bootstrap_devices(RestoreHatch(routines_error=error))

                self.assertIsInstance(restore, Restore)
                self.assertIsNone(restore.routines)


class GetRestDevicesRestoreAlarmsTest(unittest.TestCase):
    def test_configures_the_alarm_api_with_the_fetched_alarms(self):
        alarms = [{"id": 1, "active": True, "enabled": True, "time": "2026-01-05 07:00:00"}]
        api = RestoreHatch(routines=[], alarms=alarms)

        restore, rest_mini = _bootstrap_devices(api)

        self.assertTrue(restore.alarm_capable)
        self.assertTrue(restore.restore_alarms_loaded)
        self.assertEqual(restore.restore_alarms, alarms)
        self.assertEqual(restore.alarm_api_url, "https://data.hatchbaby.com/")
        self.assertEqual([mac for mac, _ in api.alarm_calls], ["11:22:33:44:55:66"])
        self.assertFalse(getattr(rest_mini, "alarm_capable", False))

    def test_a_failed_alarm_fetch_still_configures_the_api(self):
        restore, _ = _bootstrap_devices(RestoreHatch(routines=[], alarms=None))

        # Both hosts tried, nothing loaded, refresh can try again later.
        self.assertTrue(restore.alarm_capable)
        self.assertFalse(restore.restore_alarms_loaded)
        self.assertEqual(restore.restore_alarms, [])


if __name__ == "__main__":
    unittest.main()
