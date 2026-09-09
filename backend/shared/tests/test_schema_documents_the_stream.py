from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator

from shared.api.schema_hooks import CONNECTED_EVENT, TRADING_EVENTS_PATH, event_names
from tokens.events import TRADING_EVENT_TYPES

HOOK = "shared.api.schema_hooks.document_trading_events_stream"


def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


class TheStreamIsInTheSchemaTest(TestCase):

    def test_the_hook_is_registered_or_nothing_below_means_anything(self):
        self.assertIn(HOOK, settings.SPECTACULAR_SETTINGS["POSTPROCESSING_HOOKS"])

    def test_the_documented_path_is_the_routed_one(self):
        self.assertEqual(TRADING_EVENTS_PATH, reverse("trading:trading-events-stream"))

    def test_the_stream_has_a_path_in_the_generated_schema(self):
        paths = schema()["paths"]

        self.assertIn(TRADING_EVENTS_PATH, paths)
        self.assertIn("get", paths[TRADING_EVENTS_PATH])

    def test_the_stream_is_documented_as_server_sent_events(self):
        responses = schema()["paths"][TRADING_EVENTS_PATH]["get"]["responses"]

        self.assertIn("text/event-stream", responses["200"]["content"])
        self.assertIn("text/plain", responses["401"]["content"])
        self.assertIn("text/plain", responses["404"]["content"])

    def test_the_documented_events_are_the_ones_the_publisher_may_send(self):
        stream = schema()["paths"][TRADING_EVENTS_PATH]["get"]["responses"]["200"]
        documented = stream["content"]["text/event-stream"]["schema"]["x-sse-events"]

        self.assertEqual(documented, ["connected", *sorted(TRADING_EVENT_TYPES)])
        self.assertEqual(documented, event_names())
        self.assertEqual(stream["content"]["text/event-stream"]["schema"]["x-sse-connection-event"], CONNECTED_EVENT)

    def test_a_new_trading_event_type_reaches_the_schema_without_an_edit(self):
        with self.settings():
            extended = frozenset(TRADING_EVENT_TYPES | {"order_expired"})
            import shared.api.schema_hooks as hooks
            import tokens.events as events

            original = events.TRADING_EVENT_TYPES
            events.TRADING_EVENT_TYPES = extended
            hooks.TRADING_EVENT_TYPES = extended
            try:
                self.assertIn(
                    "order_expired",
                    schema()["paths"][TRADING_EVENTS_PATH]["get"]["responses"]["200"]["content"]["text/event-stream"][
                        "schema"
                    ]["x-sse-events"],
                )
            finally:
                events.TRADING_EVENT_TYPES = original
                hooks.TRADING_EVENT_TYPES = original
