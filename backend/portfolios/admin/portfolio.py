from django.contrib import admin
from django.db.models import Count

from portfolios.models.portfolio import Portfolio


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ["uuid", "user_account", "name", "wallet_count", "is_active", "created_at"]
    list_filter = ["user_account", "is_active"]
    search_fields = ["name", "user_account__account_number"]
    readonly_fields = ["uuid", "wallet_count", "created_at", "updated_at"]
    filter_horizontal = ["wallets"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(wallet_count=Count("wallets", distinct=True))

    @admin.display(description="Wallets", ordering="wallet_count")
    def wallet_count(self, obj):
        return obj.wallet_count
