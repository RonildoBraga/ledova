import json
import os
import signal
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import django


def database_identity():
    from django.db import connections

    from shared.db import current_alias

    with connections[current_alias()].cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid(), current_user")
        pid, user = cursor.fetchone()
    return {"pid": pid, "database_user": user}


def notify(stage):
    print(json.dumps({"stage": stage, **database_identity()}), flush=True)


def run():
    os.environ["DJANGO_SETTINGS_MODULE"] = "ledova_backend.settings.test_postgres"
    from django.conf import settings

    settings.DATABASES = json.loads(os.environ["ORDER_ACTION_TEST_DATABASES"])
    settings.RLS_AMBIENT_ALIAS = "app"
    settings.ALLOWED_HOSTS = ["testserver"]
    django.setup()

    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    from shared.db import current_alias
    from tokens.services import order_actions as service

    incoming = json.loads(sys.stdin.readline())
    phase = incoming["phase"]
    directory = Path(incoming["directory"])
    client = APIClient()
    client.force_authenticate(get_user_model().objects.get(pk=incoming["user_id"]))
    original_spend = service.spend
    original_apply = service._apply
    original_verify = service._verify
    original_load = service._load_action
    verifications = 0
    selections = 0

    def killed(*args, **kwargs):
        os.kill(os.getpid(), signal.SIGKILL)

    def spend_then_kill(*args):
        original_spend(*args)
        killed()

    def apply_then_kill(*args, **kwargs):
        original_apply(*args, **kwargs)
        killed()

    def verify_then_pause(*args):
        nonlocal verifications
        challenge = original_verify(*args)
        verifications += 1
        if verifications == 2:
            notify("locked")
            if sys.stdin.readline().strip() != "continue":
                raise AssertionError("The owned action worker was not released")
        return challenge

    def load_after_announcing(*args):
        nonlocal selections
        selections += 1
        if selections == 1:
            notify("selecting")
        return original_load(*args)

    def published(event, payload):
        with (directory / "events.jsonl").open("a") as output:
            output.write(json.dumps({"event": event, "alias": current_alias()}) + "\n")

    with ExitStack() as stack:
        stack.enter_context(patch("tokens.events._publish", side_effect=published))
        stack.enter_context(patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True))
        stack.enter_context(
            patch(
                "tokens.services.order_modification_service.ShareTokenService",
                side_effect=AssertionError("No provider call belongs to this buy action"),
            )
        )
        if phase == "spent":
            stack.enter_context(patch.object(service, "spend", side_effect=spend_then_kill))
        elif phase == "applied":
            stack.enter_context(patch.object(service, "_apply", side_effect=apply_then_kill))
        elif phase == "committed":
            stack.enter_context(patch("tokens.views.trading_order.action_snapshot", side_effect=killed))
        elif phase == "pause":
            stack.enter_context(patch.object(service, "_verify", side_effect=verify_then_pause))
        elif phase == "compete":
            stack.enter_context(patch.object(service, "_load_action", side_effect=load_after_announcing))
        response = client.post(
            f"/api/v1/trading/orders/{incoming['order_id']}/modify/", incoming["body"], format="json"
        )
        print(
            json.dumps(
                {
                    "status": response.status_code,
                    "body": response.json(),
                    "alias": current_alias(),
                    **database_identity(),
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    run()
