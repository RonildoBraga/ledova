import logging

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from wallets.models import Wallet
from whitelist.models import WhitelistEntry, WhitelistStatus

logger = logging.getLogger(__name__)


class WhitelistEntryAddForm(forms.ModelForm):

    wallet_address = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"style": "width: 500px; font-family: monospace;"}),
    )

    class Meta:
        model = WhitelistEntry
        fields = ["wallet_address", "notes"]

    def clean_wallet_address(self):
        address = self.cleaned_data.get("wallet_address", "").strip()

        if not address:
            raise forms.ValidationError("Wallet address is required.")

        if WhitelistEntry.objects.filter_by_address(address).exists():
            raise forms.ValidationError(f"Address '{address}' already has a whitelist entry.")

        wallet = Wallet.objects.filter_by_address(address).first()

        if not wallet:
            raise forms.ValidationError(f"Wallet '{address}' not found.")

        if not wallet.user_account:
            raise forms.ValidationError(f"Wallet '{address}' is not assigned to any user.")

        self._wallet = wallet
        return address

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.wallet = self._wallet
        if commit:
            instance.save()
        return instance


@admin.register(WhitelistEntry)
class WhitelistEntryAdmin(admin.ModelAdmin):
    list_display = [
        "short_address",
        "wallet_owner",
        "status",
        "is_whitelisted",
        "created_at",
    ]
    list_filter = [
        "status",
        "is_whitelisted",
    ]
    search_fields = [
        "wallet__address",
        "wallet__user_account__uuid",
    ]
    list_select_related = ["wallet", "wallet__user_account"]
    readonly_fields = [
        "uuid",
        "status",
        "is_whitelisted",
        "created_at",
        "updated_at",
        "add_tx_hash",
        "remove_tx_hash",
        "on_chain_timestamp",
        "last_synced_at",
        "status_actions",
    ]
    ordering = ["-created_at"]
    actions = ["add_to_blockchain", "remove_from_blockchain", "sync_with_blockchain"]

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = WhitelistEntryAddForm
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return [
                ("Add Wallet to Whitelist", {"fields": ["wallet_address"]}),
                ("Notes", {"fields": ["notes"], "classes": ["collapse"]}),
            ]
        return self._change_fieldsets

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj:
            readonly.append("wallet")
        return readonly

    _change_fieldsets = [
        ("Wallet Information", {"fields": ["uuid", "wallet"]}),
        ("Status & Actions", {"fields": ["status", "is_whitelisted", "status_actions"]}),
        (
            "Blockchain",
            {
                "fields": ["add_tx_hash", "remove_tx_hash", "on_chain_timestamp", "last_synced_at"],
                "classes": ["collapse"],
            },
        ),
        ("Notes", {"fields": ["notes"], "classes": ["collapse"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    def short_address(self, obj):
        address = obj.wallet.address
        return format_html(
            '<span title="{}">{}</span>',
            address,
            f"{address[:10]}...{address[-6:]}",
        )

    short_address.short_description = "Wallet Address"

    def wallet_owner(self, obj):
        if obj.wallet and obj.wallet.user_account:
            profiles = obj.wallet.user_account.user_profiles.all()
            if profiles:
                return profiles[0].user.email
        return mark_safe('<span style="color: #dc3545;">Unassigned</span>')

    wallet_owner.short_description = "Owner"
    wallet_owner.admin_order_field = "wallet__user_account__uuid"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<uuid:uuid>/add-to-blockchain/",
                self.admin_site.admin_view(self.add_to_blockchain_view),
                name="whitelist_whitelistentry_add_to_blockchain",
            ),
            path(
                "<uuid:uuid>/remove-from-blockchain/",
                self.admin_site.admin_view(self.remove_from_blockchain_view),
                name="whitelist_whitelistentry_remove_from_blockchain",
            ),
        ]
        return custom_urls + urls

    def status_actions(self, obj):
        if obj.pk is None:
            return "-"

        buttons = []
        base_style = (
            "display: inline-block; padding: 6px 12px; margin: 2px; "
            "text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold;"
        )

        if obj.status == WhitelistStatus.PENDING and not obj.is_whitelisted:
            add_url = reverse("admin:whitelist_whitelistentry_add_to_blockchain", args=[obj.uuid])
            buttons.append(
                f'<a href="{add_url}" style="{base_style} background-color: #28a745; color: white;">'
                "Add to Blockchain</a>"
            )
        elif obj.status == WhitelistStatus.ACTIVE and obj.is_whitelisted:
            remove_url = reverse("admin:whitelist_whitelistentry_remove_from_blockchain", args=[obj.uuid])
            buttons.append(
                f'<a href="{remove_url}" style="{base_style} background-color: #dc3545; color: white;">'
                "Remove from Blockchain</a>"
            )
        elif obj.status == WhitelistStatus.FAILED:
            add_url = reverse("admin:whitelist_whitelistentry_add_to_blockchain", args=[obj.uuid])
            buttons.append(
                f'<a href="{add_url}" style="{base_style} background-color: #ffc107; color: black;">'
                "Retry Add to Blockchain</a>"
            )

        if not buttons:
            return "-"

        return mark_safe(" ".join(buttons))

    status_actions.short_description = "Quick Actions"

    def add_to_blockchain_view(self, request, uuid):
        entry = get_object_or_404(WhitelistEntry, uuid=uuid)

        if entry.is_whitelisted:
            messages.warning(request, f"Address {entry.wallet.address} is already whitelisted on blockchain.")
            return HttpResponseRedirect(reverse("admin:whitelist_whitelistentry_change", args=[entry.pk]))

        if request.method == "POST":
            from whitelist.services import WhitelistService

            service = WhitelistService()
            result = service.ensure_whitelisted([entry])

            if result["added"] or result["synced"]:
                messages.success(request, f"Successfully whitelisted {entry.wallet.address}.")
            for error in result["errors"]:
                messages.error(request, error)

            return HttpResponseRedirect(reverse("admin:whitelist_whitelistentry_change", args=[entry.pk]))

        context = {
            **self.admin_site.each_context(request),
            "title": f"Add to Blockchain: {entry.wallet.address[:10]}...{entry.wallet.address[-6:]}",
            "entry": entry,
            "opts": self.model._meta,
        }
        return render(request, "admin/whitelist/whitelistentry/add_to_blockchain_confirm.html", context)

    def remove_from_blockchain_view(self, request, uuid):
        entry = get_object_or_404(WhitelistEntry, uuid=uuid)

        if not entry.is_whitelisted:
            messages.warning(request, f"Address {entry.wallet.address} is not on the blockchain whitelist.")
            return HttpResponseRedirect(reverse("admin:whitelist_whitelistentry_change", args=[entry.pk]))

        if request.method == "POST":
            from whitelist.services import WhitelistService

            service = WhitelistService()
            result = service.ensure_removed([entry])

            if result["removed"]:
                messages.success(request, f"Successfully removed {entry.wallet.address} from blockchain whitelist.")
            for error in result["errors"]:
                messages.error(request, error)

            return HttpResponseRedirect(reverse("admin:whitelist_whitelistentry_change", args=[entry.pk]))

        context = {
            **self.admin_site.each_context(request),
            "title": f"Remove from Blockchain: {entry.wallet.address[:10]}...{entry.wallet.address[-6:]}",
            "entry": entry,
            "opts": self.model._meta,
        }
        return render(request, "admin/whitelist/whitelistentry/remove_from_blockchain_confirm.html", context)

    @admin.action(description="Add selected entries to blockchain whitelist")
    def add_to_blockchain(self, request, queryset):
        from whitelist.services import WhitelistService

        service = WhitelistService()
        result = service.ensure_whitelisted(list(queryset))

        if result["added"]:
            self.message_user(request, f"Added {result['added']} address(es) to blockchain.", messages.SUCCESS)
        if result["synced"]:
            self.message_user(
                request, f"Synced {result['synced']} address(es) already on blockchain.", messages.SUCCESS
            )
        if result["skipped"]:
            self.message_user(request, f"Skipped {result['skipped']} already active address(es).", messages.WARNING)
        for error in result["errors"]:
            self.message_user(request, error, messages.ERROR)

    @admin.action(description="Remove selected entries from blockchain whitelist")
    def remove_from_blockchain(self, request, queryset):
        from whitelist.services import WhitelistService

        service = WhitelistService()
        result = service.ensure_removed(list(queryset))

        if result["removed"]:
            self.message_user(request, f"Removed {result['removed']} address(es) from blockchain.", messages.SUCCESS)
        if result["skipped"]:
            self.message_user(request, f"Skipped {result['skipped']} address(es) not on blockchain.", messages.WARNING)
        for error in result["errors"]:
            self.message_user(request, error, messages.ERROR)

    @admin.action(description="Sync selected entries with blockchain")
    def sync_with_blockchain(self, request, queryset):
        from whitelist.services import WhitelistService

        service = WhitelistService()
        result = service.sync_entries(list(queryset))

        if result["synced"]:
            self.message_user(request, f"Synced {result['synced']} address(es) with blockchain.", messages.SUCCESS)
        for error in result["errors"]:
            self.message_user(request, error, messages.ERROR)
