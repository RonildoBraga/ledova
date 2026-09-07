from django.db import models


class DerivesCompanyFromToken(models.Model):

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.company_id is None and self.token_id is not None:
            self.company_id = self.token.company_id
        super().save(*args, **kwargs)


class DerivesWalletsFromOrders(models.Model):

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.seller_wallet_id is None and self.sell_order_id is not None:
            self.seller_wallet_id = self.sell_order.wallet_id
        if self.buyer_wallet_id is None and self.buy_order_id is not None:
            self.buyer_wallet_id = self.buy_order.wallet_id
        super().save(*args, **kwargs)


class DerivesWalletFromOrder(models.Model):

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.wallet_id is None and self.order_id is not None:
            self.wallet_id = self.order.wallet_id
        super().save(*args, **kwargs)
