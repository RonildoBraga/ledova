from django.contrib import admin

from assets.models import AssetSnapshot


@admin.register(AssetSnapshot)
class AssetSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "asset",
        "price",
        "source_timestamp",
        "data_source",
        "block_number",
    )
    list_filter = (
        "data_source",
        "asset__asset_type",
        ("source_timestamp", admin.DateFieldListFilter),
    )
    search_fields = ("asset__symbol", "asset__name")
    list_per_page = 50
    ordering = ("-source_timestamp",)
    list_select_related = ("asset",)
    readonly_fields = [
        "asset",
        "price",
        "price_currency",
        "market_data",
        "source_timestamp",
        "data_source",
        "block_number",
        "tx_hash",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
