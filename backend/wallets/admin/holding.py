from django.contrib import admin

from wallets.models import Holding


@admin.register(Holding)
class HoldingAdmin(admin.ModelAdmin):
    list_display = (
        "uuid",
        "wallet_address_short",
        "asset_symbol",
        "quantity",
        "market_value_display",
        "last_synced_at",
    )
    list_filter = (
        "asset__asset_type",
        "asset__is_verified",
        "last_synced_at",
        "created_at",
    )
    search_fields = (
        "uuid",
        "wallet__address",
        "asset__symbol",
        "asset__name",
    )
    readonly_fields = (
        "uuid",
        "quantity",
        "market_value",
        "last_synced_block",
        "last_synced_at",
        "created_at",
        "updated_at",
    )
    ordering = ("-quantity",)
    list_select_related = ("wallet", "asset")

    fieldsets = (
        ("Wallet & Asset", {"fields": ("uuid", "wallet", "asset")}),
        ("Quantity", {"fields": ("quantity", "market_value")}),
        (
            "Sync Information",
            {
                "fields": ("last_synced_block", "last_synced_at"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def wallet_address_short(self, obj):
        return f"{obj.wallet.address[:10]}..."

    wallet_address_short.short_description = "Wallet"
    wallet_address_short.admin_order_field = "wallet__address"

    def asset_symbol(self, obj):
        return obj.asset.symbol

    asset_symbol.short_description = "Asset"
    asset_symbol.admin_order_field = "asset__symbol"

    def market_value_display(self, obj):
        value = obj.market_value
        if value:
            return f"${value:,.2f}"
        return "-"

    market_value_display.short_description = "Market Value (USD)"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
