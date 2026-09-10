import json
import os
import signal
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

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

    settings.DATABASES = json.loads(os.environ["ORDER_SUBMISSION_TEST_DATABASES"])
    settings.RLS_AMBIENT_ALIAS = "app"
    settings.ALLOWED_HOSTS = ["testserver"]
    settings.ATOMIC_SWAP_ADDRESS = "0x" + "9d" * 20
    django.setup()

    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    from shared.db import current_alias
    from tokens.services import trading_order_create as service
    from tokens.services.token_transfer_service import TokenTransferService
    from tokens.tests.order_submission_fixtures import BASE, chain_client

    incoming = json.loads(sys.stdin.readline())
    phase = incoming["phase"]
    directory = Path(incoming["directory"])
    client = APIClient()
    client.force_authenticate(get_user_model().objects.get(pk=incoming["user_id"]))
    chain = chain_client()
    whitelist = Mock()
    whitelist.is_whitelisted.return_value = True
    balance = Mock()
    balance.get_token_balance.return_value = 100
    original_spend = service.spend
    original_create = TokenTransferService.create_order_and_match
    original_find = service._find_submission

    def killed(*args, **kwargs):
        os.kill(os.getpid(), signal.SIGKILL)

    def spend_then_kill(*args):
        original_spend(*args)
        killed()

    def create_then_kill(*args, **kwargs):
        original_create(*args, **kwargs)
        killed()

    def find_then_pause(*args):
        submission = original_find(*args)
        notify("locked")
        if sys.stdin.readline().strip() != "continue":
            raise AssertionError("The owned submission worker was not released")
        return submission

    def find_after_announcing(*args):
        notify("selecting")
        return original_find(*args)

    def published(event, payload):
        with (directory / "events.jsonl").open("a") as output:
            output.write(json.dumps({"event": event, "payload": payload, "alias": current_alias()}) + "\n")

    with ExitStack() as stack:
        for target, replacement in (
            ("tokens.services.token_transfer_service.get_base_chain_client", chain),
            ("tokens.services.atomic_swap_service.get_base_chain_client", chain),
            ("tokens.services.token_transfer_service.WhitelistService", whitelist),
            ("tokens.services.atomic_swap_service.WhitelistService", whitelist),
            ("tokens.services.ShareTokenService", balance),
        ):
            stack.enter_context(patch(target, return_value=replacement))
        stack.enter_context(patch("tokens.events._publish", side_effect=published))
        stack.enter_context(patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True))
        if phase == "spent":
            stack.enter_context(patch.object(service, "spend", side_effect=spend_then_kill))
        elif phase == "matched":
            stack.enter_context(patch.object(TokenTransferService, "create_order_and_match", create_then_kill))
        elif phase == "committed":
            stack.enter_context(patch("tokens.views.trading_order.submission_snapshot", side_effect=killed))
        elif phase == "pause":
            stack.enter_context(patch.object(service, "_find_submission", side_effect=find_then_pause))
        elif phase == "compete":
            stack.enter_context(patch.object(service, "_find_submission", side_effect=find_after_announcing))
        response = client.post(f"{BASE}create/", incoming["body"], format="json")
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
