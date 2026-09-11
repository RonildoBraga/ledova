from decimal import Decimal

from django.conf import settings
from django.db import models

from shared.models import BaseModel
from tokens.querysets.order_action import OrderActionQuerySet


class OrderActionPurpose(models.TextChoices):
    CANCEL = "cancel", "Cancel"
    MODIFY = "modify", "Modify"


class OrderActionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPLIED = "applied", "Applied"
    REFUSED = "refused", "Refused"


class OrderActionSubmission(BaseModel):
    objects = OrderActionQuerySet.as_manager()

    action_id = models.UUIDField(editable=False)
    protocol_version = models.PositiveSmallIntegerField(default=1, editable=False)
    purpose = models.CharField(max_length=6, choices=OrderActionPurpose.choices, editable=False)
    owner_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT, related_name="+")
    order = models.ForeignKey("tokens.TransferOrder", on_delete=models.PROTECT, related_name="actions")
    wallet = models.ForeignKey("wallets.Wallet", on_delete=models.PROTECT, related_name="+")
    token = models.ForeignKey("tokens.ShareToken", on_delete=models.PROTECT, related_name="+")
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    wallet_address = models.CharField(max_length=42, editable=False)
    chain_id = models.PositiveBigIntegerField(editable=False)
    verifying_contract = models.CharField(max_length=42, editable=False)
    token_metadata = models.JSONField(editable=False)
    review_values = models.JSONField(editable=False)
    new_quantity = models.PositiveBigIntegerField(null=True, editable=False)
    new_min_quantity = models.PositiveBigIntegerField(null=True, editable=False)
    new_price_per_share = models.DecimalField(max_digits=18, decimal_places=2, null=True, editable=False)
    status = models.CharField(max_length=7, choices=OrderActionStatus.choices, default=OrderActionStatus.PENDING)
    executed_challenge = models.OneToOneField(
        "tokens.SigningChallenge", on_delete=models.PROTECT, related_name="action_execution", null=True, blank=True
    )
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    result = models.JSONField(null=True, blank=True)
    refusal_code = models.CharField(max_length=64, blank=True)
    refusal_detail = models.CharField(max_length=512, blank=True)
    refusal_status = models.PositiveSmallIntegerField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner_account", "action_id"], name="order_action_account_key"),
            models.CheckConstraint(
                condition=models.Q(protocol_version=1, chain_id__gt=0)
                & (
                    models.Q(
                        purpose="cancel",
                        new_quantity__isnull=True,
                        new_min_quantity__isnull=True,
                        new_price_per_share__isnull=True,
                    )
                    | models.Q(
                        purpose="modify",
                        new_quantity__isnull=False,
                        new_quantity__gt=0,
                        new_min_quantity__isnull=False,
                        new_min_quantity__gte=0,
                        new_price_per_share__isnull=False,
                        new_price_per_share__gt=0,
                        new_price_per_share__lt=Decimal("10000000000000000"),
                    )
                ),
                name="order_action_valid_intent",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status="pending",
                        executed_challenge__isnull=True,
                        executed_by__isnull=True,
                        resolved_at__isnull=True,
                        result__isnull=True,
                        refusal_code="",
                        refusal_detail="",
                        refusal_status__isnull=True,
                    )
                    | models.Q(
                        status="applied",
                        executed_challenge__isnull=False,
                        executed_by__isnull=False,
                        resolved_at__isnull=False,
                        result__isnull=False,
                        refusal_code="",
                        refusal_detail="",
                        refusal_status__isnull=True,
                    )
                    | (
                        models.Q(
                            status="refused",
                            executed_challenge__isnull=False,
                            executed_by__isnull=False,
                            resolved_at__isnull=False,
                            result__isnull=True,
                            refusal_status__isnull=False,
                        )
                        & ~models.Q(refusal_detail="")
                        & (
                            models.Q(purpose="cancel", refusal_code="order_cancellation_failed", refusal_status=400)
                            | models.Q(purpose="modify", refusal_code="order_modification_failed", refusal_status=400)
                            | models.Q(purpose="modify", refusal_code="order_modification_conflict", refusal_status=409)
                        )
                    )
                ),
                name="order_action_outcome_shape",
            ),
        ]
