from django.db import models
from django.utils import timezone


class SigningChallengeQuerySet(models.QuerySet):
    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()

        from wallets.models import Wallet

        addresses = Wallet.objects.visible_to_user(user).values_list("address", flat=True)
        return self.filter(wallet_address__in=addresses)

    def spendable(self):
        return self.filter(consumed_at__isnull=True, expires_at__gt=timezone.now())

    def expired_and_unspent(self, cutoff=None):
        return self.filter(consumed_at__isnull=True, expires_at__lte=cutoff or timezone.now())

    def purgeable(self, cutoff, batch: int):
        return self.filter(pk__in=self.expired_and_unspent(cutoff).order_by("expires_at").values("pk")[:batch])
