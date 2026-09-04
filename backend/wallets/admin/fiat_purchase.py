from django.contrib import admin

from wallets.models import FiatTransaction


@admin.register(FiatTransaction)
class FiatTransactionAdmin(admin.ModelAdmin):
    list_display = [
        "external_id",
        "user",
        "wallet",
        "fiat_amount",
        "fiat_currency",
        "crypto_amount",
        "crypto_currency",
        "status",
        "provider",
        "created_at",
    ]
    list_filter = ["status", "provider", "crypto_currency", "fiat_currency", "created_at"]
    search_fields = ["external_id", "user__email", "wallet__address", "transaction_hash"]
    readonly_fields = [
        "uuid",
        "created_at",
        "updated_at",
        "completed_at",
        "failed_at",
        "external_id",
        "transaction_hash",
        "provider_data",
    ]
