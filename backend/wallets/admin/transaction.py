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
    fieldsets = (
        (
            "Transaction Information",
            {
                "fields": (
                    "tx_hash",
                    "chain",
                    "from_address",
                    "to_address",
                    "status",
                )
            },
        ),
        (
            "Asset & Amount",
            {
                "fields": (
                    "asset",
                    "amount",
                    "market_value",
                    "transaction_fee_estimated",
                    "transaction_fee",
                )
            },
        ),
        (
            "Block Details",
            {
                "fields": (
                    "block_number",
                    "block_timestamp",
                )
            },
        ),
        (
            "Wallet",
            {"fields": ("wallet",)},
        ),
        (
            "System Information",
            {
                "fields": ("uuid", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def tx_hash_short(self, obj):
        return f"{obj.tx_hash[:16]}..." if obj.tx_hash else "-"

    tx_hash_short.short_description = "TX Hash"

    def from_address_short(self, obj):
        return f"{obj.from_address[:10]}..." if obj.from_address else "-"

    from_address_short.short_description = "From"

    def to_address_short(self, obj):
        return f"{obj.to_address[:10]}..." if obj.to_address else "-"

    to_address_short.short_description = "To"

    def market_value_display(self, obj):
        if obj.market_value is not None:
            return f"${obj.market_value:,.2f}"
        return "-"

    market_value_display.short_description = "USD Value"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("asset", "wallet")
