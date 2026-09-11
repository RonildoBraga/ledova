from collections import Counter
from datetime import timedelta

from django.db.models import F, Q
from django.utils import timezone

from ledova_backend.procrastinate_app import app
from shared.db import use_operator
from wallets.models import BitcoinSubmission, WalletSubmission
from wallets.services.chain_observations import observe_wallet_chain

OBSERVATION_BATCH_SIZE = 25


@app.periodic(cron="*/5 * * * *")
@app.task
def observe_wallet_chains(timestamp: int):
    cutoff = timezone.now() - timedelta(minutes=2)
    candidates = []
    with use_operator():
        for model in (WalletSubmission, BitcoinSubmission):
            rows = (
                model.objects.filter(
                    Q(transaction__chain_watch__last_started_at__isnull=True)
                    | Q(transaction__chain_watch__last_started_at__lte=cutoff)
                )
                .order_by(F("transaction__chain_watch__last_started_at").asc(nulls_first=True), "created_at", "pk")
                .values_list("transaction__chain_watch__last_started_at", "created_at", "transaction_id")[
                    :OBSERVATION_BATCH_SIZE
                ]
            )
            candidates.extend(rows)
    candidates.sort(key=lambda row: (row[0] is not None, row[0] or row[1], row[1], str(row[2])))
    outcomes = Counter(
        observe_wallet_chain(tx_id, reconcile=True) for _, _, tx_id in candidates[:OBSERVATION_BATCH_SIZE]
    )
    return {"attempted": sum(outcomes.values()), "outcomes": dict(outcomes)}
