from django.contrib import admin

from wallets.models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "tx_hash_short",
        "chain",
        "from_address_short",
        "to_address_short",
        "asset",
        "amount",
        "market_value_display",
        "transaction_fee",
        "status",
        "block_timestamp",
    )
    search_fields = (
        "tx_hash",
        "from_address",
        "to_address",
        "wallet__address",
        "asset__symbol",
    )
    list_filter = (
        "chain",
        "block_timestamp",
        "asset",
        "status",
    )
    readonly_fields = ("uuid", "created_at", "updated_at")
    list_select_related = ("asset", "wallet")

    @admin.display(description="TX Hash")
    def tx_hash_short(self, obj):
        return f"{obj.tx_hash[:16]}..." if obj.tx_hash else "-"

    @admin.display(description="From")
    def from_address_short(self, obj):
        return f"{obj.from_address[:10]}..." if obj.from_address else "-"

    @admin.display(description="To")
    def to_address_short(self, obj):
        return f"{obj.to_address[:10]}..." if obj.to_address else "-"

    @admin.display(description="USD Value")
    def market_value_display(self, obj):
        if obj.market_value is not None:
            return f"${obj.market_value:,.2f}"
        return "-"
