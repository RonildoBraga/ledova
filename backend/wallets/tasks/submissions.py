from collections import Counter

from django.db.models import F

from ledova_backend.procrastinate_app import app
from shared.db import use_operator
from wallets.models import WalletSubmission
from wallets.services.submissions import attempt_submission


@app.periodic(cron="*/5 * * * *")
@app.task
def recover_wallet_submissions(timestamp: int):
    with use_operator():
        pending = (
            WalletSubmission.objects.filter(transaction__status="pending")
            .order_by(F("last_attempt_at").asc(nulls_first=True), "created_at", "pk")
            .values_list("pk", flat=True)[:100]
        )
        outcomes = Counter(attempt_submission(submission_id) for submission_id in list(pending))
    return {"attempted": sum(outcomes.values()), "outcomes": dict(outcomes)}
