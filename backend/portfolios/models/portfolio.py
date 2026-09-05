from django.db import models

from portfolios.querysets.portfolio import PortfolioQuerySet
from shared.models import BaseModel
from users.models import UserAccount


class Portfolio(BaseModel):
    user_account = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name="portfolios")
    name = models.CharField(max_length=255)
    wallets = models.ManyToManyField("wallets.Wallet", related_name="portfolios", blank=True)
    is_active = models.BooleanField(default=True)

    objects = PortfolioQuerySet.as_manager()

    class Meta:
        db_table = "portfolios"
        verbose_name = "Portfolio"
        verbose_name_plural = "Portfolios"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or f"Portfolio for {self.user_account}"

    def account_wallets(self):
        return self.wallets.filter(user_account_id=self.user_account_id)
