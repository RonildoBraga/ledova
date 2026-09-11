from collections import Counter

from django.db.models import F

from ledova_backend.procrastinate_app import app
from shared.db import use_operator
from wallets.models import BitcoinSubmission, WalletSubmission
from wallets.services.bitcoin_submissions import attempt_bitcoin_submission
from wallets.services.submissions import attempt_submission


@app.periodic(cron="*/5 * * * *")
@app.task
def recover_wallet_submissions(timestamp: int):
    with use_operator():
        pending = []
        for model, attempt in (
            (WalletSubmission, attempt_submission),
            (BitcoinSubmission, attempt_bitcoin_submission),
        ):
            rows = (
                model.objects.filter(transaction__status="pending")
                .order_by(F("last_attempt_at").asc(nulls_first=True), "created_at", "pk")
                .values_list("last_attempt_at", "created_at", "pk")[:100]
            )
            pending.extend((last, created, pk, attempt) for last, created, pk in rows)
        pending.sort(key=lambda row: (row[0] is not None, row[0] or row[1], row[1], str(row[2])))
        outcomes = Counter(attempt(submission_id) for _, _, submission_id, attempt in pending[:100])
    return {"attempted": sum(outcomes.values()), "outcomes": dict(outcomes)}
