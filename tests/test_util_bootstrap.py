"""Tests for device discovery and MQTT connection setup."""

import asyncio
from collections.abc import Callable
import sys
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import MagicMock, patch

import pytest

from hatch_rest_api import util_bootstrap


class FakeHatch:
    """Stands in for the Hatch REST client, returning canned payloads."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Create a fake client with a mock session."""
        self.api_session = MagicMock()

    async def login(self, **kwargs: Any) -> str:
        """Return a fixed auth token."""
        return "auth-token"

    async def iot_devices(self, **kwargs: Any) -> list[dict[str, str]]:
        """Return a single Rest Mini."""
        return [
            {
                "product": "restMini",
                "name": "Nursery",
                "thingName": "thing-1",
                "macAddress": "AA:BB:CC:DD:EE:FF",
            }
        ]

    async def token(self, **kwargs: Any) -> dict[str, str]:
        """Return a fixed AWS IoT token payload."""
        return {
            "region": "us-east-1",
            "identityId": "identity-1",
            "token": "aws-token",
            "endpoint": "https://example-ats.iot.us-east-1.amazonaws.com",
        }


class FakeAwsHttp:
    """Stands in for the Cognito client, returning fixed credentials."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Accept and ignore any constructor arguments."""

    async def aws_credentials(self, **kwargs: Any) -> dict[str, dict[str, Any]]:
        """Return fixed AWS credentials."""
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

    def __getattr__(self, name: str) -> Callable[..., Any]:
        """Return a stub for any subscribe_* or publish_* method."""
        if name.startswith("subscribe_"):
            return lambda *args, **kwargs: (MagicMock(), MagicMock())
        return lambda *args, **kwargs: MagicMock()


class FlakyMqttConnection:
    """MQTT connection whose first ``connect`` futures raise ``error``.

    awscrt's ``connect`` never raises inline; it hands the exception to the
    future it returns, so the failure surfaces from ``future.result()``.
    """

    def __init__(self, error: BaseException, failures: int = 1) -> None:
        """Fail the first ``failures`` connects with ``error``."""
        self.error = error
        self.remaining_failures = failures
        self.connect_calls = 0

    def connect(self) -> MagicMock:
        """Return a connect future, failing it while failures remain."""
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

    def __init__(self, arity: int) -> None:
        """Accept exactly ``arity`` positional arguments."""
        self.arity = arity
        self.calls: list[tuple[Any, ...]] = []

    def __call__(self, *args: Any) -> None:
        """Record the call, or raise like the native extension on a count mismatch."""
        if len(args) != self.arity:
            raise TypeError(f"function takes exactly {self.arity} arguments ({len(args)} given)")
        self.calls.append(args)


def _run_bootstrap(
    io_mock: MagicMock | None = None, connection: Any = None
) -> tuple[MagicMock, MagicMock]:
    """Run get_rest_devices with every network dependency faked.

    Returns the patched connection builder and the patched awscrt ``io`` module
    so tests can assert on how each was used. Pass an ``io_mock`` to share one
    across several runs, which is how a reconnect is simulated, or a
    ``connection`` to control what the builder hands back.
    """
    builder = MagicMock(return_value=MagicMock() if connection is None else connection)
    if io_mock is None:
        io_mock = MagicMock()

    with (
        patch.object(util_bootstrap, "Hatch", FakeHatch),
        patch.object(util_bootstrap, "Contentful", MagicMock()),
        patch.object(util_bootstrap, "AwsHttp", FakeAwsHttp),
        patch.object(util_bootstrap, "AwsCredentialsProvider", MagicMock()),
        patch.object(util_bootstrap, "io", io_mock),
        patch.object(util_bootstrap, "IotShadowClient", lambda *a, **kw: FakeShadowClient()),
        patch.object(util_bootstrap, "websockets_with_default_aws_signing", builder),
    ):
        asyncio.run(util_bootstrap.get_rest_devices(email="user@example.com", password="hunter2"))

    return builder, io_mock


class GetRestDevicesClientBootstrapTest(unittest.TestCase):
    """Regression guard for the awscrt event loop thread leak.

    ``get_rest_devices`` used to build an EventLoopGroup, DefaultHostResolver
    and ClientBootstrap of its own on every call. awscrt starts a native thread
    per EventLoopGroup and only stops it once the native resource is destroyed,
    which never happened while the connection graph stayed reachable. Since
    callers reconnect every time the AWS credentials expire -- hourly -- each
    refresh stranded another thread, pipe pair and set of CRT buffers.
    """

    def test_uses_shared_static_bootstrap(self) -> None:
        """Uses shared static bootstrap."""
        _, io_mock = _run_bootstrap()

        io_mock.ClientBootstrap.get_or_create_static_default.assert_called_once()

    def test_does_not_build_per_connection_event_loop_group(self) -> None:
        """Does not build per connection event loop group."""
        _, io_mock = _run_bootstrap()

        io_mock.EventLoopGroup.assert_not_called()
        io_mock.DefaultHostResolver.assert_not_called()

    def test_reconnects_reuse_the_same_bootstrap(self) -> None:
        """Reconnects reuse the same bootstrap."""
        io_mock = MagicMock()
        builder_one, _ = _run_bootstrap(io_mock)
        builder_two, _ = _run_bootstrap(io_mock)

        assert (
            builder_one.call_args.kwargs["client_bootstrap"]
            is builder_two.call_args.kwargs["client_bootstrap"]
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

    def test_metrics_collection_disabled(self) -> None:
        """Metrics collection disabled."""
        builder, _ = _run_bootstrap()

        builder.assert_called_once()
        assert builder.call_args.kwargs["enable_metrics_collection"] is False

    def test_devices_still_created(self) -> None:
        """Devices still created."""
        builder, _ = _run_bootstrap()

        # Sanity check that disabling metrics did not disturb the rest of the
        # bootstrap: the connection is still built and devices still returned.
        assert builder.call_args.kwargs["endpoint"] == "example-ats.iot.us-east-1.amazonaws.com"


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

    def _native(self, arity: int) -> tuple[SimpleNamespace, FakeNativeBinding]:
        binding = FakeNativeBinding(arity)
        return SimpleNamespace(mqtt_client_connection_connect=binding), binding

    def test_trims_the_argument_the_extension_does_not_take(self) -> None:
        """Trims the argument the extension does not take."""
        native, binding = self._native(17)
        connection = FlakyMqttConnection(
            TypeError("function takes exactly 17 arguments (18 given)")
        )

        with patch.dict(sys.modules, {"_awscrt": native}):
            _run_bootstrap(connection=connection)
            native.mqtt_client_connection_connect(*range(18))

        assert connection.connect_calls == 2
        assert binding.calls == [tuple(range(17))]

    def test_pads_the_argument_the_extension_expects(self) -> None:
        """Pads the argument the extension expects."""
        native, binding = self._native(18)
        connection = FlakyMqttConnection(
            TypeError("function takes exactly 18 arguments (17 given)")
        )

        with patch.dict(sys.modules, {"_awscrt": native}):
            _run_bootstrap(connection=connection)
            native.mqtt_client_connection_connect(*range(17))

        assert connection.connect_calls == 2
        assert binding.calls == [(*tuple(range(17)), None)]

    def test_leaves_unrelated_type_errors_alone(self) -> None:
        """Leaves unrelated type errors alone."""
        native, binding = self._native(17)
        connection = FlakyMqttConnection(
            TypeError("connect() got an unexpected keyword argument 'username'")
        )

        with (
            patch.dict(sys.modules, {"_awscrt": native}),
            pytest.raises(TypeError),
        ):
            _run_bootstrap(connection=connection)

        assert connection.connect_calls == 1
        assert native.mqtt_client_connection_connect is binding

    def test_leaves_gaps_wider_than_one_argument_alone(self) -> None:
        """Trimming a wider gap would feed the binding other parameters."""
        native, binding = self._native(15)
        connection = FlakyMqttConnection(
            TypeError("function takes exactly 15 arguments (18 given)")
        )

        with (
            patch.dict(sys.modules, {"_awscrt": native}),
            pytest.raises(TypeError),
        ):
            _run_bootstrap(connection=connection)

        assert connection.connect_calls == 1
        assert native.mqtt_client_connection_connect is binding

    def test_retries_only_once(self) -> None:
        """Retries only once."""
        native, _ = self._native(17)
        connection = FlakyMqttConnection(
            TypeError("function takes exactly 17 arguments (18 given)"),
            failures=2,
        )

        with (
            patch.dict(sys.modules, {"_awscrt": native}),
            pytest.raises(TypeError),
        ):
            _run_bootstrap(connection=connection)

        assert connection.connect_calls == 2


if __name__ == "__main__":
    unittest.main()
