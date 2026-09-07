from unittest.mock import Mock, patch
from uuid import uuid4

from django.db import transaction
from django.test import TestCase

from tokens.events import publish_trading_event


@patch("tokens.events._get_redis_client")
class TradingEventsWaitForTheCommitTest(TestCase):

    def test_a_rolled_back_write_publishes_nothing(self, get_client):
        client = Mock()
        get_client.return_value = client

        try:
            with transaction.atomic():
                publish_trading_event("order_cancelled", str(uuid4()))
                raise RuntimeError("the write failed after the event was queued")
        except RuntimeError:
            pass

        client.publish.assert_not_called()

    def test_a_committed_write_publishes_once(self, get_client):
        client = Mock()
        get_client.return_value = client
        token_uuid = str(uuid4())

        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                publish_trading_event("order_cancelled", token_uuid)

        client.publish.assert_called_once()

    def test_an_unsupported_event_is_refused_before_anything_is_queued(self, get_client):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            publish_trading_event("not_an_event", str(uuid4()))

        self.assertEqual(callbacks, [])
        get_client.assert_not_called()
