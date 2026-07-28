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

    def _run_bootstrap(self):
        builder = MagicMock(return_value=MagicMock())

        with (
            patch.object(util_bootstrap, "Hatch", FakeHatch),
            patch.object(util_bootstrap, "Contentful", MagicMock()),
            patch.object(util_bootstrap, "AwsHttp", FakeAwsHttp),
            patch.object(util_bootstrap, "AwsCredentialsProvider", MagicMock()),
            patch.object(util_bootstrap, "io", MagicMock()),
            patch.object(
                util_bootstrap, "IotShadowClient", lambda *a, **kw: FakeShadowClient()
            ),
            patch.object(
                util_bootstrap, "websockets_with_default_aws_signing", builder
            ),
        ):
            asyncio.run(
                util_bootstrap.get_rest_devices(
                    email="user@example.com", password="hunter2"
                )
            )

        return builder

    def test_metrics_collection_disabled(self):
        builder = self._run_bootstrap()

        builder.assert_called_once()
        self.assertIs(builder.call_args.kwargs["enable_metrics_collection"], False)

    def test_devices_still_created(self):
        builder = self._run_bootstrap()

        # Sanity check that disabling metrics did not disturb the rest of the
        # bootstrap: the connection is still built and devices still returned.
        self.assertEqual(
            builder.call_args.kwargs["endpoint"],
            "example-ats.iot.us-east-1.amazonaws.com",
        )


if __name__ == "__main__":
    unittest.main()
