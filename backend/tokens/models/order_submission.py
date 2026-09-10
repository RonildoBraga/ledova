from decimal import Decimal

from django.conf import settings
from django.db import models

from shared.models import BaseModel
from tokens.models.choices import TransferOrderType
from tokens.querysets.order_submission import OrderSubmissionQuerySet


class OrderSubmissionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CREATED = "created", "Created"
    REFUSED = "refused", "Refused"


class OrderSubmission(BaseModel):
    objects = OrderSubmissionQuerySet.as_manager()

    submission_id = models.UUIDField(editable=False)
    owner_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT, related_name="+")
    wallet = models.ForeignKey("wallets.Wallet", on_delete=models.PROTECT, related_name="+")
    token = models.ForeignKey("tokens.ShareToken", on_delete=models.PROTECT, related_name="+")
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    intent_version = models.PositiveSmallIntegerField(default=1, editable=False)
    wallet_address = models.CharField(max_length=42, editable=False)
    order_type = models.CharField(max_length=10, choices=TransferOrderType.choices, editable=False)
    quantity = models.PositiveBigIntegerField(editable=False)
    min_quantity = models.PositiveBigIntegerField(default=0, editable=False)
    price_per_share = models.DecimalField(max_digits=18, decimal_places=2, editable=False)
    chain_id = models.PositiveBigIntegerField(editable=False)
    verifying_contract = models.CharField(max_length=42, editable=False)
    token_metadata = models.JSONField(editable=False)
    status = models.CharField(
        max_length=7, choices=OrderSubmissionStatus.choices, default=OrderSubmissionStatus.PENDING
    )
    order = models.OneToOneField(
        "tokens.TransferOrder", on_delete=models.PROTECT, related_name="submission", null=True, blank=True
    )
    executed_challenge = models.OneToOneField(
        "tokens.SigningChallenge", on_delete=models.PROTECT, related_name="execution", null=True, blank=True
    )
    initial_counter_order = models.ForeignKey(
        "tokens.TransferOrder", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    initial_swap = models.ForeignKey(
        "tokens.SwapOrder", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    refusal_code = models.CharField(max_length=32, blank=True)
    refusal_detail = models.CharField(max_length=200, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner_account", "submission_id"], name="order_submission_account_key"),
            models.CheckConstraint(
                condition=models.Q(intent_version=1, quantity__gt=0, chain_id__gt=0)
                & models.Q(min_quantity__gte=0, min_quantity__lte=models.F("quantity"))
                & models.Q(price_per_share__gt=0, price_per_share__lt=Decimal("10000000000000000"))
                & models.Q(order_type__in=TransferOrderType.values),
                name="order_submission_valid_terms",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status="pending",
                        order__isnull=True,
                        executed_challenge__isnull=True,
                        resolved_at__isnull=True,
                        refusal_code="",
                        refusal_detail="",
                        initial_counter_order__isnull=True,
                        initial_swap__isnull=True,
                    )
                    | models.Q(
                        status="created",
                        order__isnull=False,
                        executed_challenge__isnull=False,
                        resolved_at__isnull=False,
                        refusal_code="",
                        refusal_detail="",
                    )
                    | (
                        models.Q(
                            status="refused",
                            order__isnull=True,
                            executed_challenge__isnull=False,
                            resolved_at__isnull=False,
                            refusal_code__in=["not_whitelisted", "insufficient_balance"],
                            initial_counter_order__isnull=True,
                            initial_swap__isnull=True,
                        )
                        & ~models.Q(refusal_detail="")
                    )
                ),
                name="order_submission_outcome_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(initial_counter_order__isnull=True, initial_swap__isnull=True)
                    | models.Q(initial_counter_order__isnull=False, initial_swap__isnull=False)
                ),
                name="order_submission_match_pair",
            ),
        ]
