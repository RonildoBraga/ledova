import logging

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse

from tokens.models import MintRequest
from tokens.services import mint_service

from ._helpers import MintForm, active_badge, format_units, hex_column

logger = logging.getLogger(__name__)


class MintableTokenAdmin(admin.ModelAdmin):
    mint_request_field = ""
    search_fields = ["name", "symbol", "contract_address"]
    ordering = ["symbol"]
    contract_address_short = hex_column("contract_address", "Contract", tail=8)
    is_active_badge = active_badge

    def get_urls(self):
        mint = path(
            "<uuid:uuid>/mint/",
            self.admin_site.admin_view(self.mint_view),
            name=f"{self.opts.app_label}_{self.opts.model_name}_mint",
        )
        return [mint] + super().get_urls()

    def mint_url(self, obj):
        return reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_mint", args=[obj.uuid])

    def mint_view(self, request, uuid):
        token = get_object_or_404(self.model, uuid=uuid)
        change_url = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_change", args=[token.pk])

        if not token.is_active:
            messages.error(request, f"Cannot mint: {token.symbol} is not active")
            return HttpResponseRedirect(change_url)
        if not token.contract_address:
            messages.error(request, f"Cannot mint: {token.symbol} has no contract address")
            return HttpResponseRedirect(change_url)

        try:
            service = mint_service.token_service(token)
            current_supply = format_units(service.get_total_supply(), token.decimals)
            is_minter = service.is_minter(service.signer_address)
        except Exception as exc:
            logger.error(f"Failed to get {token.symbol} contract info: {exc}")
            current_supply, is_minter = "Error", False

        form = MintForm(request.POST or None, decimals=token.decimals, symbol=token.symbol)
        if request.method == "POST" and form.is_valid():
            mint_request = MintRequest.objects.create(
                **{self.mint_request_field: token},
                recipient_address=form.cleaned_data["recipient_address"],
                recipient_name=form.cleaned_data["recipient_name"],
                amount=form.cleaned_data["amount"],
                deposit_reference=form.cleaned_data["deposit_reference"],
                deposit_date=form.cleaned_data["deposit_date"],
                notes=form.cleaned_data["notes"],
                requested_by=request.user,
            )
            try:
                tx_hash, _ = mint_service.execute(mint_request, request.user)
                messages.success(
                    request,
                    f"Successfully minted {mint_request.amount_display} {token.symbol} "
                    f"to {mint_request.recipient_name} (tx: {tx_hash[:16]}...)",
                )
            except Exception as exc:
                messages.error(request, f"Minting failed: {exc}")
            return HttpResponseRedirect(reverse("admin:tokens_mintrequest_change", args=[mint_request.pk]))

        context = {
            **self.admin_site.each_context(request),
            "title": f"Mint {token.symbol}",
            "subtitle": None,
            "token": token,
            "form": form,
            "opts": self.opts,
            "current_supply": current_supply,
            "is_minter": is_minter,
        }
        return render(request, "admin/tokens/mint_form.html", context)
