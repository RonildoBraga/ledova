from django.db.models import BigIntegerField, Max, QuerySet, Subquery, Sum, Value
from django.db.models.functions import Cast, Coalesce

from tokens.models.choices import IssuanceStatus

ISSUANCE_KEY_PREFIX = "issuance-request:"


def completed_supply_annotation(token_ref):
    from tokens.models import ShareIssuance

    totals = (
        ShareIssuance.objects.completed()
        .exclude(amount="")
        .filter(token=token_ref)
        .values("token")
        .annotate(total=Sum(Cast("amount", BigIntegerField())))
        .values("total")
    )
    return Coalesce(Subquery(totals, output_field=BigIntegerField()), Value(0), output_field=BigIntegerField())


class ShareIssuanceQuerySet(QuerySet):

    def filter_by_token(self, token):
        if token:
            return self.filter(token=token)
        return self

    def filter_by_date_range(self, start_date=None, end_date=None):
        qs = self
        if start_date:
            qs = qs.filter(completed_at__gte=start_date)
        if end_date:
            qs = qs.filter(completed_at__lte=end_date)
        return qs

    def completed(self):
        return self.filter(status=IssuanceStatus.COMPLETED)

    def broadcast(self):
        return self.exclude(tx_hash__isnull=True).exclude(tx_hash="")

    def unconfirmed_request_uuids(self):
        keys = self.broadcast().exclude(status=IssuanceStatus.COMPLETED).values_list("idempotency_key", flat=True)
        return [key[len(ISSUANCE_KEY_PREFIX) :] for key in keys if key and key.startswith(ISSUANCE_KEY_PREFIX)]

    def completed_supply(self, token) -> int:
        total = (
            self.completed()
            .filter(token=token)
            .exclude(amount="")
            .aggregate(total=Sum(Cast("amount", BigIntegerField())))["total"]
        )
        return int(total or 0)

    def pending(self):
        return self.filter(status=IssuanceStatus.PENDING)

    def with_token(self):
        return self.select_related("token")

    def with_initiated_by(self):
        return self.select_related("initiated_by")

    def unique_holders_with_names(self):
        latest_per_address = self.completed().values("recipient_address").annotate(latest_created=Max("created_at"))
        address_names = {}
        addresses_with_latest = {item["recipient_address"]: item["latest_created"] for item in latest_per_address}

        for issuance in (
            self.completed().filter(recipient_address__in=addresses_with_latest.keys()).order_by("-created_at")
        ):
            addr = issuance.recipient_address
            if addr not in address_names:
                address_names[addr] = issuance.recipient_name

        return address_names

    def holders_with_aggregated_balances(self):
        return (
            self.completed()
            .values("recipient_address", "recipient_name")
            .annotate(total_balance=Sum(Cast("amount", BigIntegerField())))
            .order_by("-total_balance")
        )

    def holders_as_list(self):
        holders = []
        for item in self.holders_with_aggregated_balances():
            try:
                balance = int(item["total_balance"]) if item["total_balance"] else 0
            except (ValueError, TypeError):
                balance = 0

            if balance > 0:
                holders.append(
                    {
                        "address": item["recipient_address"],
                        "name": item.get("recipient_name") or None,
                        "balance": str(balance),
                        "source": "issuances",
                    }
                )
        return holders
