import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as ReadTimeout

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse

from integrations.base_chain.exceptions import BaseChainConnectionError
from tokens.exceptions import (
    CompanyNotReadyException,
    InvalidTokenStateException,
    TokenPauseFailedException,
)
from tokens.models import IssuanceStatus, ShareIssuance, ShareToken, ShareTokenStatus
from tokens.services import ShareTokenService

from ._helpers import action_buttons, hex_column, status_badge

logger = logging.getLogger(__name__)

# Seconds the change page waits for paused(); a slower node gets both buttons instead of holding the page.
PAUSED_READ_TIMEOUT = 5

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
            path(
                "<uuid:uuid>/retry-deploy/",
                self.admin_site.admin_view(self.retry_deploy_view),
                name="tokens_sharetoken_retry_deploy",
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
            retry_url = reverse("admin:tokens_sharetoken_retry_deploy", args=[obj.uuid])
            return action_buttons(
                [("⏳ Deployment in Progress", None, "#17a2b8"), ("↻ Retry Deployment", retry_url, "#007bff")]
            )

        unpause_url = reverse("admin:tokens_sharetoken_unpause", args=[obj.uuid])
        if obj.status == ShareTokenStatus.DEPLOYED:
            # A pause whose receipt was lost leaves the DB deployed while the chain is paused: the chain decides
            # which button is shown (one eth_call per change page); both are offered when it cannot be read.
            pause_url = reverse("admin:tokens_sharetoken_pause", args=[obj.uuid])
            paused_on_chain = self._paused_on_chain(obj)
            if paused_on_chain is True:
                return action_buttons([("▶ Unpause Token", unpause_url, "#28a745")])
            buttons = [("⏸ Pause Token", pause_url, "#ffc107", "black")]
            if paused_on_chain is None:
                buttons.append(("▶ Unpause Token", unpause_url, "#6c757d"))
            return action_buttons(buttons)

        if obj.status == ShareTokenStatus.PAUSED:
            return action_buttons([("▶ Unpause Token", unpause_url, "#28a745")])

        return "-"

    @staticmethod
    def _paused_on_chain(obj):
        """paused() as the chain reports it, or None when it cannot be read in PAUSED_READ_TIMEOUT seconds.

        Any error (a slow or unreachable node, a misconfigured factory or ABI path, a settings error) is logged and
        answered with None: the change page offers both buttons rather than failing on the chain.
        """
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            return executor.submit(lambda: ShareTokenService().read_paused(obj)).result(timeout=PAUSED_READ_TIMEOUT)
        except ReadTimeout:
            logger.warning(
                f"paused() of {obj.symbol} not answered within {PAUSED_READ_TIMEOUT}s; offering both buttons"
            )
            return None
        except Exception as exc:
            logger.warning(f"paused() of {obj.symbol} could not be read: {exc}")
            return None
        finally:
            executor.shutdown(wait=False)

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
                f"Deployment started for '{token.name}'. No shares are minted at deployment; "
                f"up to {token.total_supply} shares can be issued through issuance requests.",
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

    def retry_deploy_view(self, request, uuid):
        """Confirm on GET and re-queue on POST: the change-page button is a link, so the state change needs a submit."""
        token = get_object_or_404(ShareToken, uuid=uuid)
        change_url = reverse("admin:tokens_sharetoken_change", args=[token.pk])
        try:
            if request.method == "POST":
                ShareTokenService.retry_deployment(token)
            else:
                ShareTokenService.require_retryable(token)
        except InvalidTokenStateException as exc:
            messages.error(request, f"Cannot retry deployment: {exc.detail}")
            return HttpResponseRedirect(change_url)

        if request.method == "POST":
            messages.info(
                request, f"Deployment retried for '{token.name}'; the task adopts or resumes what is on chain."
            )
            return HttpResponseRedirect(change_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Retry Deployment: {token.name}",
            "subtitle": None,
            "token": token,
            "opts": self.model._meta,
        }
        return render(request, "admin/tokens/sharetoken/retry_deploy_confirm.html", context)

    def pause_view(self, request, uuid):
        return self._pause_view(request, uuid, "pause")

    def unpause_view(self, request, uuid):
        return self._pause_view(request, uuid, "unpause")

    def _pause_view(self, request, uuid, verb):
        """The service holds the state guard, so a deployed token the chain reports paused unpauses in one click."""
        token = get_object_or_404(ShareToken, uuid=uuid)
        change_url = reverse("admin:tokens_sharetoken_change", args=[token.pk])
        try:
            getattr(ShareTokenService(), verb)(token)
        except (InvalidTokenStateException, TokenPauseFailedException, BaseChainConnectionError) as exc:
            messages.error(request, f"Cannot {verb}: {getattr(exc, 'detail', exc)}")
            return HttpResponseRedirect(change_url)
        if verb == "pause":
            messages.warning(request, f"Token '{token.name}' has been paused on chain. Transfers are now disabled.")
        else:
            messages.success(request, f"Token '{token.name}' has been unpaused on chain. Transfers are now enabled.")
        return HttpResponseRedirect(change_url)


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
