import unittest
from concurrent.futures import Future
from unittest.mock import MagicMock

from hatch_rest_api.shadow_client_subscriber import ShadowClientSubscriberMixin


class RecordingShadowClient:
    """IotShadowClient stub that records subscribe/unsubscribe traffic.

    Subscribing hands back the (future, topic) pair the real client returns,
    with a topic derived from the thing name so assertions can name it.
    """

    def __init__(self, unsubscribe_error: Exception | None = None):
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self._unsubscribe_error = unsubscribe_error

    def _subscribe(self, kind, request, **kwargs):
        topic = f"$aws/things/{request.thing_name}/shadow/{kind}/accepted"
        self.subscribed.append(topic)
        done: Future = Future()
        done.set_result(None)
        return done, topic

    def subscribe_to_update_shadow_accepted(self, request, **kwargs):
        return self._subscribe("update", request)

    def subscribe_to_get_shadow_accepted(self, request, **kwargs):
        return self._subscribe("get", request)

    def unsubscribe(self, topic):
        self.unsubscribed.append(topic)
        result: Future = Future()
        if self._unsubscribe_error is not None:
            result.set_exception(self._unsubscribe_error)
        else:
            result.set_result(None)
        return result

    def publish_get_shadow(self, **kwargs):
        done: Future = Future()
        done.set_result(MagicMock())
        return done


class Device(ShadowClientSubscriberMixin):
    """Minimal concrete subscriber; every real device type is one of these."""

    def _update_local_state(self, state):
        pass


def _device(shadow_client):
    return Device(
        device_name="Nursery",
        thing_name="thing-1",
        mac="AA:BB:CC:DD:EE:FF",
        shadow_client=shadow_client,
    )


class UnsubscribeTest(unittest.TestCase):
    def test_subscribed_topics_are_retained(self):
        client = RecordingShadowClient()
        device = _device(client)

        # The topics used to be logged and dropped, which left no way to undo
        # the subscriptions that pin the connection graph.
        self.assertEqual(device._subscribed_topics, client.subscribed)
        self.assertEqual(len(device._subscribed_topics), 2)

    def test_unsubscribe_releases_every_subscription(self):
        client = RecordingShadowClient()
        device = _device(client)

        device.unsubscribe()

        self.assertCountEqual(client.unsubscribed, client.subscribed)
        self.assertEqual(device._subscribed_topics, [])

    def test_unsubscribe_is_idempotent(self):
        client = RecordingShadowClient()
        device = _device(client)

        device.unsubscribe()
        device.unsubscribe()

        # A second pass must not re-send: the coordinator calls this on both
        # the reconnect and the shutdown path, which can overlap.
        self.assertEqual(len(client.unsubscribed), 2)

    def test_unsubscribe_survives_a_dead_connection(self):
        # Credentials expiring can drop the connection before we get to
        # unsubscribe. The UNSUBACK never arrives, but the topics still have to
        # be cleared -- the teardown releases the same native references.
        client = RecordingShadowClient(unsubscribe_error=RuntimeError("connection closed"))
        device = _device(client)

        device.unsubscribe()

        self.assertEqual(device._subscribed_topics, [])
        self.assertEqual(len(client.unsubscribed), 2)


if __name__ == "__main__":
    unittest.main()
