from django.contrib import admin

from wallets.models import HoldingSnapshot


@admin.register(HoldingSnapshot)
class HoldingSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "uuid",
        "holding_wallet_short",
        "holding_asset",
        "quantity",
        "snapshot_date",
        "snapshot_reason",
        "block_number",
        "created_at",
    ]
    list_filter = [
        "snapshot_reason",
        "snapshot_date",
        "holding__asset",
        "holding__wallet",
        ("snapshot_date", admin.DateFieldListFilter),
    ]
    search_fields = [
        "uuid",
        "holding__wallet__address",
        "holding__asset__symbol",
        "holding__asset__name",
        "caused_by_transaction__tx_hash",
    ]
    readonly_fields = [
        "uuid",
        "holding",
        "quantity",
        "snapshot_date",
        "snapshot_reason",
        "block_number",
        "caused_by_transaction",
        "transaction_hash",
        "created_at",
        "updated_at",
    ]
    list_select_related = [
        "holding",
        "holding__wallet",
        "holding__asset",
        "caused_by_transaction",
    ]
    list_per_page = 50
    ordering = ["-snapshot_date", "-created_at"]

    @admin.display(description="Wallet", ordering="holding__wallet__address")
    def holding_wallet_short(self, obj):
        return f"{obj.holding.wallet.address[:10]}..."

    @admin.display(description="Asset", ordering="holding__asset__symbol")
    def holding_asset(self, obj):
        return obj.holding.asset.symbol

    @admin.display(description="Transaction Hash")
    def transaction_hash(self, obj):
        if obj.caused_by_transaction:
            return obj.caused_by_transaction.tx_hash
        return "-"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
