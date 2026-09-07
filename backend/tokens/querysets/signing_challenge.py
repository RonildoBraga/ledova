from django.db import models
from django.utils import timezone


class SigningChallengeQuerySet(models.QuerySet):
    def expired_and_unspent(self, cutoff=None):
        return self.filter(consumed_at__isnull=True, expires_at__lte=cutoff or timezone.now())

    def purgeable(self, cutoff, batch: int):
        return self.filter(pk__in=self.expired_and_unspent(cutoff).order_by("expires_at").values("pk")[:batch])
