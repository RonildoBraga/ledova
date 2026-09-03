"""Authorization and disclosure regressions for the trading SSE endpoint."""

import json
from unittest.mock import Mock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from authentication.services.tokens import TokenService
from companies.models import Company
from feature_flags.models import FeatureFlag
from tokens.events import (
    TRADING_EVENT_TYPES,
    TRADING_EVENTS_CHANNEL,
    publish_trading_event,
)
from tokens.models import ShareToken
from tokens.models.choices import ShareTokenStatus, ShareTokenType
from tokens.views.trading_events import _event_stream, _format_public_trading_event

User = get_user_model()


async def _empty_stream():
    if False:
        yield ""


class _FakePubSub:
    def __init__(self, messages, subscribe_error=None, unsubscribe_error=None):
        self.messages = list(messages)
        self.subscribe_error = subscribe_error
        self.unsubscribe_error = unsubscribe_error
        self.subscribed_to = None
        self.unsubscribed_from = None
        self.closed = False

    async def subscribe(self, channel):
        self.subscribed_to = channel
        if self.subscribe_error:
            raise self.subscribe_error

    async def get_message(self, **_kwargs):
        return self.messages.pop(0) if self.messages else None

    async def unsubscribe(self, channel):
        self.unsubscribed_from = channel
        if self.unsubscribe_error:
            raise self.unsubscribe_error

    async def aclose(self):
        self.closed = True


class _FakeRedis:
    def __init__(self, pubsub):
        self._pubsub = pubsub
        self.closed = False

    def pubsub(self):
        return self._pubsub

    async def aclose(self):
        self.closed = True


class TradingEventDisclosureTest(SimpleTestCase):
    @patch("tokens.events._get_redis_client")
    def test_publisher_payload_contains_no_order_or_swap_identifier(self, get_client):
        client = Mock()
        get_client.return_value = client
        token_uuid = str(uuid4())

        publish_trading_event("order_created", token_uuid)

        client.publish.assert_called_once()
        channel, raw_payload = client.publish.call_args.args
        self.assertEqual(channel, TRADING_EVENTS_CHANNEL)
        self.assertEqual(json.loads(raw_payload), {"event": "order_created", "token": token_uuid})

    @patch("tokens.events._get_redis_client")
    def test_publisher_refuses_unknown_event_type(self, get_client):
        publish_trading_event("unknown_event", str(uuid4()))

        get_client.assert_not_called()

    def test_every_public_event_type_discards_private_payload(self):
        token_uuid = str(uuid4())
        order_uuid = str(uuid4())
        swap_uuid = str(uuid4())

        for event_type in TRADING_EVENT_TYPES:
            with self.subTest(event_type=event_type):
                formatted = _format_public_trading_event(
                    {
                        "event": event_type,
                        "token": token_uuid,
                        "data": {"order_uuid": order_uuid, "swap_uuid": swap_uuid},
                    },
                    token_uuid,
                )
                self.assertEqual(formatted, f"event: {event_type}\ndata: {{}}\n\n")
                self.assertNotIn(order_uuid, formatted)
                self.assertNotIn(swap_uuid, formatted)

    async def test_stream_skips_wrong_token_unknown_and_malformed_events(self):
        token_uuid = str(uuid4())
        other_token_uuid = str(uuid4())
        order_uuid = str(uuid4())
        swap_uuid = str(uuid4())
        pubsub = _FakePubSub(
            [
                {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "event": "order_created",
                            "token": other_token_uuid,
                            "data": {"order_uuid": order_uuid},
                        }
                    ),
                },
                {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "event": "unknown_event",
                            "token": token_uuid,
                            "data": {"swap_uuid": swap_uuid},
                        }
                    ),
                },
                {"type": "message", "data": json.dumps([])},
                {"type": "message", "data": b"\xff"},
                {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "event": "order_created",
                            "token": token_uuid,
                            "data": {"order_uuid": order_uuid, "swap_uuid": swap_uuid},
                        }
                    ),
                },
            ]
        )
        client = _FakeRedis(pubsub)

        with patch("tokens.views.trading_events.aioredis.from_url", return_value=client):
            stream = _event_stream(token_uuid)
            connected = await anext(stream)
            public_event = await anext(stream)
            await stream.aclose()

        self.assertEqual(connected, 'event: connected\ndata: {"status": "ok"}\n\n')
        self.assertEqual(public_event, "event: order_created\ndata: {}\n\n")
        self.assertNotIn(order_uuid, public_event)
        self.assertNotIn(swap_uuid, public_event)
        self.assertEqual(pubsub.subscribed_to, TRADING_EVENTS_CHANNEL)
        self.assertEqual(pubsub.unsubscribed_from, TRADING_EVENTS_CHANNEL)
        self.assertTrue(pubsub.closed)
        self.assertTrue(client.closed)

    async def test_subscribe_failure_closes_pubsub_and_client(self):
        pubsub = _FakePubSub([], subscribe_error=ConnectionError("subscribe failed"))
        client = _FakeRedis(pubsub)

        with patch("tokens.views.trading_events.aioredis.from_url", return_value=client):
            stream = _event_stream(str(uuid4()))
            with self.assertRaises(ConnectionError):
                await anext(stream)

        self.assertIsNone(pubsub.unsubscribed_from)
        self.assertTrue(pubsub.closed)
        self.assertTrue(client.closed)

    async def test_unsubscribe_failure_still_closes_pubsub_and_client(self):
        pubsub = _FakePubSub([], unsubscribe_error=ConnectionError("unsubscribe failed"))
        client = _FakeRedis(pubsub)

        with patch("tokens.views.trading_events.aioredis.from_url", return_value=client):
            stream = _event_stream(str(uuid4()))
            await anext(stream)
            with self.assertRaises(ConnectionError):
                await stream.aclose()

        self.assertEqual(pubsub.unsubscribed_from, TRADING_EVENTS_CHANNEL)
        self.assertTrue(pubsub.closed)
        self.assertTrue(client.closed)


class TradingEventsAuthorizationTest(TestCase):
    endpoint = "/api/v1/trading/events/stream/"

    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.issuer = User.objects.create_user(
            email="issuer@sse.example.test",
            password="pw-12345678",
            is_active=True,
        )
        self.investor = User.objects.create_user(
            email="investor@sse.example.test",
            password="pw-12345678",
            is_active=True,
        )
        self.investor_access, self.investor_refresh = TokenService.issue(self.investor)
        self.company = Company.objects.create(
            owner=self.issuer,
            name="SSE Market Pty Ltd",
            company_type="private",
            acn="123456789",
            status="active",
        )
        self.deployed_token = self._make_token("LIVE", ShareTokenStatus.DEPLOYED)
        self.draft_token = self._make_token("DRAFT", ShareTokenStatus.DRAFT)
        self.paused_token = self._make_token("PAUSE", ShareTokenStatus.PAUSED)

    def _make_token(self, symbol, status):
        return ShareToken.objects.create(
            company=self.company,
            name=f"{symbol} Ordinary",
            symbol=symbol,
            token_type=ShareTokenType.ORDINARY,
            total_supply="1000",
            status=status,
            contract_address="0x" + symbol.lower().ljust(40, "0") if status == ShareTokenStatus.DEPLOYED else None,
        )

    def _authenticate_cookie(self, access_token):
        self.client.cookies["access"] = access_token

    @patch("tokens.views.trading_events._event_stream", side_effect=lambda _token_uuid: _empty_stream())
    def test_unrelated_investor_can_subscribe_to_deployed_market_token(self, event_stream):
        self._authenticate_cookie(self.investor_access)

        response = self.client.get(self.endpoint, {"token": str(self.deployed_token.uuid)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertEqual(response["Cache-Control"], "no-cache")
        self.assertEqual(response["X-Accel-Buffering"], "no")
        event_stream.assert_called_once_with(str(self.deployed_token.uuid))

    @patch("tokens.views.trading_events._event_stream", side_effect=lambda _token_uuid: _empty_stream())
    def test_authorization_header_can_subscribe_to_deployed_market_token(self, event_stream):
        response = self.client.get(
            self.endpoint,
            {"token": str(self.deployed_token.uuid)},
            HTTP_AUTHORIZATION=f"Bearer {self.investor_access}",
        )

        self.assertEqual(response.status_code, 200)
        event_stream.assert_called_once_with(str(self.deployed_token.uuid))

    @patch("tokens.views.trading_events._event_stream", side_effect=lambda _token_uuid: _empty_stream())
    def test_nonpublic_and_unknown_targets_are_indistinguishable(self, event_stream):
        self._authenticate_cookie(self.investor_access)
        targets = (
            None,
            "not-a-uuid",
            str(uuid4()),
            str(self.draft_token.uuid),
            str(self.paused_token.uuid),
        )

        for target in targets:
            with self.subTest(target=target):
                params = {} if target is None else {"token": target}
                response = self.client.get(self.endpoint, params)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.content, b"Token not found")

        event_stream.assert_not_called()

    @patch("tokens.views.trading_events._event_stream", side_effect=lambda _token_uuid: _empty_stream())
    def test_staff_receives_the_same_public_target_boundary(self, event_stream):
        staff = User.objects.create_user(
            email="staff@sse.example.test",
            password="pw-12345678",
            is_staff=True,
            is_active=True,
        )
        self._authenticate_cookie(TokenService.issue(staff)[0])

        deployed_response = self.client.get(self.endpoint, {"token": str(self.deployed_token.uuid)})
        draft_response = self.client.get(self.endpoint, {"token": str(self.draft_token.uuid)})

        self.assertEqual(deployed_response.status_code, 200)
        self.assertEqual(draft_response.status_code, 404)
        self.assertEqual(draft_response.content, b"Token not found")
        event_stream.assert_called_once_with(str(self.deployed_token.uuid))

    @patch("tokens.views.trading_events._event_stream", side_effect=lambda _token_uuid: _empty_stream())
    def test_anonymous_request_is_rejected_before_stream_creation(self, event_stream):
        response = self.client.get(self.endpoint, {"token": str(self.deployed_token.uuid)})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.content, b"Unauthorized")
        event_stream.assert_not_called()

    @patch("tokens.views.trading_events._event_stream", side_effect=lambda _token_uuid: _empty_stream())
    def test_revoked_cookie_token_is_rejected_before_stream_creation(self, event_stream):
        self._authenticate_cookie(self.investor_access)
        TokenService.revoke(self.investor_refresh)

        response = self.client.get(self.endpoint, {"token": str(self.deployed_token.uuid)})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.content, b"Unauthorized")
        event_stream.assert_not_called()

    @patch("tokens.views.trading_events._event_stream", side_effect=lambda _token_uuid: _empty_stream())
    def test_disabled_user_is_rejected_before_stream_creation(self, event_stream):
        self._authenticate_cookie(self.investor_access)
        self.investor.is_active = False
        self.investor.save(update_fields=["is_active"])

        response = self.client.get(self.endpoint, {"token": str(self.deployed_token.uuid)})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.content, b"Unauthorized")
        event_stream.assert_not_called()

    @patch("tokens.views.trading_events._event_stream", side_effect=lambda _token_uuid: _empty_stream())
    def test_active_query_token_remains_supported_until_issue_three(self, event_stream):
        response = self.client.get(
            self.endpoint,
            {
                "token": str(self.deployed_token.uuid),
                "auth": self.investor_access,
            },
        )

        self.assertEqual(response.status_code, 200)
        event_stream.assert_called_once_with(str(self.deployed_token.uuid))

    @patch("tokens.views.trading_events._event_stream", side_effect=lambda _token_uuid: _empty_stream())
    def test_query_token_uses_the_normal_revocation_boundary(self, event_stream):
        access_token = self.investor_access
        TokenService.revoke(self.investor_refresh)

        response = self.client.get(
            self.endpoint,
            {"token": str(self.deployed_token.uuid), "auth": access_token},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.content, b"Unauthorized")
        event_stream.assert_not_called()
