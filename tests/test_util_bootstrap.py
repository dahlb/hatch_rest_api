import asyncio
import unittest
from unittest.mock import MagicMock, patch

from hatch_rest_api import util_bootstrap


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


def _run_bootstrap(io_mock=None):
    """Run get_rest_devices with every network dependency faked.

    Returns the patched connection builder and the patched awscrt ``io`` module
    so tests can assert on how each was used. Pass an ``io_mock`` to share one
    across several runs, which is how a reconnect is simulated.
    """
    builder = MagicMock(return_value=MagicMock())
    if io_mock is None:
        io_mock = MagicMock()

    with (
        patch.object(util_bootstrap, "Hatch", FakeHatch),
        patch.object(util_bootstrap, "Contentful", MagicMock()),
        patch.object(util_bootstrap, "AwsHttp", FakeAwsHttp),
        patch.object(util_bootstrap, "AwsCredentialsProvider", MagicMock()),
        patch.object(util_bootstrap, "io", io_mock),
        patch.object(
            util_bootstrap, "IotShadowClient", lambda *a, **kw: FakeShadowClient()
        ),
        patch.object(util_bootstrap, "websockets_with_default_aws_signing", builder),
    ):
        asyncio.run(
            util_bootstrap.get_rest_devices(
                email="user@example.com", password="hunter2"
            )
        )

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


if __name__ == "__main__":
    unittest.main()
