from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse

from tokens.exceptions import CompanyNotReadyException, InvalidTokenStateException
from tokens.models import IssuanceStatus, ShareIssuance, ShareToken, ShareTokenStatus
from tokens.services import ShareTokenService

from ._helpers import action_buttons, hex_column, status_badge

ISSUANCE_COLORS = {
    IssuanceStatus.PENDING: "#6c757d",
    IssuanceStatus.PROCESSING: "#17a2b8",
    IssuanceStatus.COMPLETED: "#28a745",
    IssuanceStatus.FAILED: "#dc3545",
}


class ShareIssuanceInline(admin.TabularInline):
    model = ShareIssuance
    extra = 0
    fields = [
        "recipient_address_short",
        "amount",
        "issuance_type",
        "status_badge",
        "tx_hash_short",
        "created_at",
    ]
    readonly_fields = [
        "recipient_address_short",
        "amount",
        "issuance_type",
        "status_badge",
        "tx_hash_short",
        "created_at",
    ]
    can_delete = False
    max_num = 0

    recipient_address_short = hex_column("recipient_address", "Recipient")
    tx_hash_short = hex_column("tx_hash", "Tx Hash")
    status_badge = status_badge(ISSUANCE_COLORS)


@admin.register(ShareToken)
class ShareTokenAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "symbol",
        "company",
        "token_type",
        "status_badge",
        "total_supply",
        "contract_address_short",
        "created_at",
    ]
    list_filter = ["status", "token_type", "is_transferable", "is_divisible"]
    search_fields = ["name", "symbol", "contract_address", "company__name"]
    readonly_fields = [
        "uuid",
        "contract_address",
        "deployment_tx_hash",
        "deployed_at",
        "created_at",
        "updated_at",
        "status_actions",
    ]
    ordering = ["-created_at"]

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))

        if obj and obj.status in [ShareTokenStatus.DEPLOYED, ShareTokenStatus.PAUSED, ShareTokenStatus.DEPLOYING]:
            deployed_readonly = [
                "company",
                "name",
                "symbol",
                "token_type",
                "total_supply",
                "decimals",
                "is_transferable",
                "is_divisible",
            ]
            for field in deployed_readonly:
                if field not in readonly:
                    readonly.append(field)

        return readonly

    fieldsets = [
        (
            "Token Information",
            {
                "fields": ["uuid", "company", "name", "symbol", "token_type"],
            },
        ),
        (
            "Status & Actions",
            {
                "fields": ["status", "status_actions"],
            },
        ),
        (
            "Token Configuration",
            {
                "fields": ["total_supply", "decimals", "is_transferable", "is_divisible"],
            },
        ),
        (
            "Blockchain",
            {
                "fields": ["contract_address", "deployment_tx_hash", "deployed_at"],
                "classes": ["collapse"],
            },
        ),
        (
            "Timestamps",
            {
                "fields": ["created_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]

    inlines = [ShareIssuanceInline]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<uuid:uuid>/deploy/",
                self.admin_site.admin_view(self.deploy_view),
                name="tokens_sharetoken_deploy",
            ),
            path(
                "<uuid:uuid>/pause/",
                self.admin_site.admin_view(self.pause_view),
                name="tokens_sharetoken_pause",
            ),
            path(
                "<uuid:uuid>/unpause/",
                self.admin_site.admin_view(self.unpause_view),
                name="tokens_sharetoken_unpause",
            ),
        ]
        return custom_urls + urls

    status_badge = status_badge(
        {
            ShareTokenStatus.DRAFT: "#6c757d",
            ShareTokenStatus.DEPLOYING: "#17a2b8",
            ShareTokenStatus.DEPLOYED: "#28a745",
            ShareTokenStatus.PAUSED: ("#ffc107", "black"),
        }
    )
    contract_address_short = hex_column("contract_address", "Contract", tail=8)

    @admin.display(description="Quick Actions")
    def status_actions(self, obj):
        if obj.pk is None:
            return "-"

        if obj.status == ShareTokenStatus.DRAFT:
            try:
                ShareTokenService.require_deployable(obj)
            except CompanyNotReadyException as exc:
                return action_buttons([(f"⚠ {exc.detail}", None, "#e9ecef", "#6c757d")])
            deploy_url = reverse("admin:tokens_sharetoken_deploy", args=[obj.uuid])
            return action_buttons([("🚀 Deploy Token", deploy_url, "#007bff")])

        if obj.status == ShareTokenStatus.DEPLOYING:
            return action_buttons([("⏳ Deployment in Progress", None, "#17a2b8")])

        if obj.status == ShareTokenStatus.DEPLOYED:
            pause_url = reverse("admin:tokens_sharetoken_pause", args=[obj.uuid])
            return action_buttons([("⏸ Pause Token", pause_url, "#ffc107", "black")])

        if obj.status == ShareTokenStatus.PAUSED:
            unpause_url = reverse("admin:tokens_sharetoken_unpause", args=[obj.uuid])
            return action_buttons([("▶ Unpause Token", unpause_url, "#28a745")])

        return "-"

    def deploy_view(self, request, uuid):
        token = get_object_or_404(ShareToken, uuid=uuid)
        change_url = reverse("admin:tokens_sharetoken_change", args=[token.pk])

        try:
            if request.method == "POST":
                ShareTokenService.start_deployment(token)
            else:
                primary_wallet = ShareTokenService.require_deployable(token)
        except (InvalidTokenStateException, CompanyNotReadyException) as exc:
            messages.error(request, f"Cannot deploy: {exc.detail}")
            return HttpResponseRedirect(change_url)

        if request.method == "POST":
            messages.success(
                request,
                f"Deployment started for '{token.name}'. "
                f"All {token.total_supply} shares will be minted to the company wallet.",
            )
            return HttpResponseRedirect(change_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Deploy Token: {token.name}",
            "subtitle": None,
            "token": token,
            "primary_wallet": primary_wallet,
            "opts": self.model._meta,
        }
        return render(request, "admin/tokens/sharetoken/deploy_confirm.html", context)

    def pause_view(self, request, uuid):
        token = get_object_or_404(ShareToken, uuid=uuid)

        if token.status != ShareTokenStatus.DEPLOYED:
            messages.error(request, f"Cannot pause: token status is '{token.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:tokens_sharetoken_change", args=[token.pk]))

        token.mark_paused()
        messages.warning(request, f"Token '{token.name}' has been paused. Transfers are now disabled.")
        return HttpResponseRedirect(reverse("admin:tokens_sharetoken_change", args=[token.pk]))

    def unpause_view(self, request, uuid):
        token = get_object_or_404(ShareToken, uuid=uuid)

        if token.status != ShareTokenStatus.PAUSED:
            messages.error(request, f"Cannot unpause: token status is '{token.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:tokens_sharetoken_change", args=[token.pk]))

        token.mark_unpaused()
        messages.success(request, f"Token '{token.name}' has been unpaused. Transfers are now enabled.")
        return HttpResponseRedirect(reverse("admin:tokens_sharetoken_change", args=[token.pk]))


@admin.register(ShareIssuance)
class ShareIssuanceAdmin(admin.ModelAdmin):
    list_display = [
        "token",
        "recipient_address_short",
        "amount",
        "issuance_type",
        "status_badge",
        "created_at",
    ]
    list_filter = ["status", "issuance_type", "token__company"]
    search_fields = ["recipient_address", "tx_hash", "token__symbol", "token__name"]
    readonly_fields = [
        "uuid",
        "token",
        "recipient_address",
        "recipient_name",
        "amount",
        "issuance_type",
        "reason",
        "status",
        "error_message",
        "tx_hash",
        "block_number",
        "gas_used",
        "initiated_by",
        "processed_at",
        "completed_at",
        "idempotency_key",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    recipient_address_short = hex_column("recipient_address", "Recipient")
    status_badge = status_badge(ISSUANCE_COLORS)
