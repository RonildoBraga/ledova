from django.db import models

from shared.models import BaseModel

WATCH_CHECK_FIELDS = frozenset(
    {
        "generation",
        "target_fingerprint",
        "last_started_at",
        "last_completed_at",
        "latest_observation",
        "latest_observation_id",
        "updated_at",
    }
)


class ChainObservationResult(models.TextChoices):
    UNKNOWN = "unknown", "Unknown"
    INCLUDED = "included", "Included"
    ORPHANED = "orphaned", "Orphaned"


class ChainObservationFinality(models.TextChoices):
    UNKNOWN = "unknown", "Unknown"
    WAITING = "waiting", "Waiting"
    SATISFIED = "satisfied", "Policy satisfied"


class ChainWatchQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if set(kwargs) - WATCH_CHECK_FIELDS:
            raise ValueError("A chain watch cannot change its recorded identity.")
        return super().update(**kwargs)

    def delete(self):
        raise ValueError("A chain watch cannot discard its recorded identity.")


class WalletChainWatch(BaseModel):
    transaction = models.OneToOneField("wallets.Transaction", on_delete=models.PROTECT, related_name="chain_watch")
    wallet = models.ForeignKey("wallets.Wallet", on_delete=models.PROTECT, related_name="chain_watches")
    user_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT, related_name="+")
    chain = models.CharField(max_length=20, editable=False)
    network = models.CharField(max_length=80, editable=False)
    tx_hash = models.CharField(max_length=66, editable=False)
    generation = models.PositiveBigIntegerField(default=0, editable=False)
    target_fingerprint = models.CharField(max_length=64, blank=True, editable=False)
    last_started_at = models.DateTimeField(null=True, editable=False, db_index=True)
    last_completed_at = models.DateTimeField(null=True, editable=False)
    latest_observation = models.ForeignKey(
        "wallets.WalletChainObservation", on_delete=models.PROTECT, null=True, related_name="+", editable=False
    )

    objects = ChainWatchQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(network__regex=r"^(evm:[1-9][0-9]*|bitcoin:[0-9a-f]{64})$"),
                name="wallet_watch_network",
            ),
            models.CheckConstraint(condition=models.Q(tx_hash__regex=r"^(0x)?[0-9a-f]{64}$"), name="wallet_watch_hash"),
            models.CheckConstraint(
                condition=(
                    models.Q(generation=0, target_fingerprint="", last_started_at__isnull=True)
                    | models.Q(
                        generation__gt=0,
                        target_fingerprint__regex=r"^[0-9a-f]{64}$",
                        last_started_at__isnull=False,
                    )
                ),
                name="wallet_watch_claim",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            fields = kwargs.get("update_fields")
            if not fields or set(fields) - WATCH_CHECK_FIELDS:
                raise ValueError("A chain watch cannot change its recorded identity.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("A chain watch cannot discard its recorded identity.")


class ChainObservationQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Chain observations cannot be rewritten.")

    def delete(self):
        raise ValueError("Chain observations cannot be deleted.")


class WalletChainObservation(BaseModel):
    watch = models.ForeignKey(WalletChainWatch, on_delete=models.PROTECT, related_name="observations")
    user_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT, related_name="+")
    generation = models.PositiveBigIntegerField(editable=False)
    target_fingerprint = models.CharField(max_length=64, editable=False)
    started_at = models.DateTimeField(editable=False)
    result = models.CharField(max_length=16, choices=ChainObservationResult.choices, editable=False)
    finality = models.CharField(max_length=16, choices=ChainObservationFinality.choices, editable=False)
    reason = models.CharField(max_length=64, blank=True, editable=False)
    policy = models.JSONField(default=dict, editable=False)
    evidence = models.JSONField(default=dict, editable=False)

    objects = ChainObservationQuerySet.as_manager()

    class Meta:
        ordering = ["-generation"]
        constraints = [
            models.UniqueConstraint(fields=["watch", "generation"], name="wallet_observation_generation"),
            models.CheckConstraint(condition=models.Q(generation__gt=0), name="wallet_observation_claim"),
            models.CheckConstraint(
                condition=models.Q(target_fingerprint__regex=r"^[0-9a-f]{64}$"), name="wallet_observation_target"
            ),
            models.CheckConstraint(
                condition=models.Q(result__in=ChainObservationResult.values), name="wallet_observation_result"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(finality=ChainObservationFinality.UNKNOWN)
                    | models.Q(
                        result=ChainObservationResult.INCLUDED,
                        finality__in=[ChainObservationFinality.WAITING, ChainObservationFinality.SATISFIED],
                    )
                ),
                name="wallet_observation_finality",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Chain observations cannot be rewritten.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Chain observations cannot be deleted.")
