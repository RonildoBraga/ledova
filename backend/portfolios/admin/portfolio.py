from django.contrib import admin

from portfolios.models.portfolio import (
    AssetAllocation,
    Portfolio,
    PortfolioSnapshot,
)


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ["uuid", "user_account", "name", "wallet_count", "is_active", "created_at"]
    list_filter = ["user_account", "is_active"]
    search_fields = ["name", "user_account__account_number"]
    readonly_fields = ["uuid", "wallet_count", "created_at", "updated_at"]
    filter_horizontal = ["wallets"]

    def wallet_count(self, obj):
        return obj.wallets.count()

    wallet_count.short_description = "Wallets"


@admin.register(AssetAllocation)
class AssetAllocationAdmin(admin.ModelAdmin):
    list_display = ["uuid", "portfolio", "asset", "percentage", "created_at", "updated_at"]
    list_filter = ["portfolio", "asset"]
    search_fields = ["portfolio__name", "asset__name", "asset__symbol"]
    readonly_fields = ["uuid", "created_at", "updated_at"]


@admin.register(PortfolioSnapshot)
class PortfolioSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "uuid",
        "portfolio",
        "snapshot_reason",
        "snapshot_date",
        "asset_count",
        "total_market_value_display",
        "created_at",
    ]
    list_filter = [
        "snapshot_reason",
        "snapshot_date",
        "portfolio",
        "portfolio__user_account",
        ("snapshot_date", admin.DateFieldListFilter),
    ]
    search_fields = ["portfolio__name", "portfolio__user_account__account_number"]
    readonly_fields = [
        "uuid",
        "portfolio",
        "snapshot_date",
        "snapshot_reason",
        "holdings_data",
        "total_market_value",
        "asset_count",
        "created_at",
        "updated_at",
    ]
    list_select_related = ["portfolio", "portfolio__user_account"]
    list_per_page = 50
    ordering = ["-snapshot_date", "-created_at"]

    def asset_count(self, obj):
        return len(obj.holdings_data) if obj.holdings_data else 0

    asset_count.short_description = "Assets"

    def total_market_value_display(self, obj):
        if obj.total_market_value:
            return f"${obj.total_market_value:,.2f}"
        return "-"

    total_market_value_display.short_description = "Market Value"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
