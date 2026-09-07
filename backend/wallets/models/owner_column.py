from django.db import models


class DerivesAccountFromWallet(models.Model):

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.user_account_id is None and self.wallet_id is not None:
            self.user_account_id = self.wallet.user_account_id
        super().save(*args, **kwargs)
