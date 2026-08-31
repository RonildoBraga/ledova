import csv
from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponse
from django.template.response import TemplateResponse

from assets.models import Asset, AssetChainDeployment
from assets.services import AssetSyncService


class AssetChainDeploymentInline(admin.TabularInline):
    model = AssetChainDeployment
    extra = 0
    fields = ("chain", "contract_address", "decimals", "is_active")
    readonly_fields = ("uuid", "created_at")


class PriceUpdateForm(forms.Form):
    price = forms.DecimalField(
        max_digits=40, decimal_places=18, required=False, help_text="New price for selected assets"
    )
    currency = forms.CharField(
        max_length=16, initial="USD", required=False, help_text="Price currency (e.g., USD, EUR)"
    )
    create_snapshot = forms.BooleanField(initial=True, required=False, help_text="Create historical price snapshot")


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        "symbol",
        "name",
        "asset_type",
        "display_chains",
        "current_price",
        "price_currency",
        "is_active",
        "is_verified",
    )
    search_fields = ("symbol", "name", "chain_deployments__contract_address")
    list_filter = (
        "asset_type",
        "is_active",
        "is_verified",
    )
    list_per_page = 100
    readonly_fields = ("uuid", "created_at", "updated_at")
    inlines = [AssetChainDeploymentInline]

    fieldsets = (
        ("Basic Information", {"fields": ("uuid", "symbol", "name", "is_active", "is_verified")}),
        ("Classification", {"fields": ("asset_type", "decimals")}),
        ("Pricing", {"fields": ("current_price", "price_currency")}),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Chains")
    def display_chains(self, obj):
        chains = obj.chain_deployments.values_list("chain", flat=True)
        return ", ".join(chains) if chains else "—"

    actions = ["update_prices", "mark_as_active", "mark_as_inactive", "export_to_csv"]

    def update_prices(self, request, queryset):
        if "apply" in request.POST:
            form = PriceUpdateForm(request.POST)
            if form.is_valid():
                price = form.cleaned_data.get("price")
                currency = form.cleaned_data.get("currency") or "USD"
                create_snapshot = form.cleaned_data.get("create_snapshot", True)

                if not price:
                    self.message_user(request, "Price is required", level=messages.ERROR)
                    return None

                success_count = 0
                error_count = 0

                for asset in queryset:
                    try:
                        AssetSyncService.update_price(
                            asset=asset,
                            price=Decimal(str(price)),
                            source="manual",
                            currency=currency,
                            create_snapshot=create_snapshot,
                        )
                        success_count += 1
                    except Exception:
                        error_count += 1

                if error_count > 0:
                    self.message_user(
                        request,
                        f"Updated {success_count} prices, {error_count} failed",
                        level=messages.WARNING,
                    )
                else:
                    self.message_user(request, f"Successfully updated prices for {success_count} assets")
                return None

        form = PriceUpdateForm()
        return TemplateResponse(
            request,
            "admin/assets/asset/update_prices.html",
            context={
                "form": form,
                "assets": queryset,
                "opts": self.model._meta,
                "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
            },
        )

    update_prices.short_description = "Update prices for selected assets"

    def mark_as_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} assets marked as active.")

    mark_as_active.short_description = "Mark selected assets as active"

    def mark_as_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} assets marked as inactive.")

    mark_as_inactive.short_description = "Mark selected assets as inactive"

    def export_to_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="assets_export.csv"'

        writer = csv.writer(response)

        writer.writerow(
            [
                "UUID",
                "Symbol",
                "Name",
                "Asset Type",
                "Chain",
                "Contract Address",
                "Decimals",
                "Current Price",
                "Price Currency",
                "Is Active",
                "Created At",
            ]
        )

        for asset in queryset:
            writer.writerow(
                [
                    asset.uuid,
                    asset.symbol,
                    asset.name,
                    asset.asset_type,
                    asset.chain or "",
                    asset.contract_address or "",
                    asset.decimals,
                    asset.current_price or "",
                    asset.price_currency,
                    "Yes" if asset.is_active else "No",
                    asset.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                ]
            )

        self.message_user(request, f"Exported {queryset.count()} assets to CSV.")
        return response

    export_to_csv.short_description = "Export selected assets to CSV"
