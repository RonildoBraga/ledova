from typing import NamedTuple

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company
from offerings.models import Offering, Subscription
from operators.models import MAX_PAYMENT_REFERENCE_PREFIX, Operator
from operators.settlement import deployment_on_chain
from tokens.models import (
    CapitalIncreaseRequest,
    ShareIssuance,
    ShareIssuanceRequest,
    ShareToken,
)
from tokens.tasks.deployment import PENDING_DEPLOYMENT_AGE
from users.models import InvestorClassification
from whitelist.models import WhitelistEntry

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_DANGER = "danger"

OPERATOR_IDENTITY_FIELDS = ("name", "legal_name", "abn", "contact_email")

OPERATOR_INCOMPLETE = "Fill in {fields} on the operator row."
OPERATOR_COMPLETE = "Identity and contact details are recorded."
SETTING_MISSING = "{name} is not set, so the contract cannot be reached."
SETTING_PRESENT = "{name} is set."
PREFIX_MISSING = "No payment reference prefix is set, so no subscription reference can be issued."
PREFIX_TOO_LONG = (
    "The prefix {prefix} is {length} characters; a reference is the prefix plus an eight-character code and "
    "an AU lodgement reference holds eighteen, so keep the prefix to {maximum}."
)
PREFIX_OK = "{prefix} leaves room for the eight-character code."
NO_SETTLEMENT_ASSETS = (
    "No settlement asset is supported, so an offering can only be paid by bank transfer. A fresh install starts "
    "this way; add one on the operator row."
)
SETTLEMENT_NOT_DEPLOYED = "{symbols} has no active deployment on {chain}."
SETTLEMENT_OK = "{count} settlement asset(s) deployed on {chain}."

REGISTRANT_NOTE = (
    "This records who keeps the register on this deployment. It does not decide who carries the section 168 "
    "obligation."
)


class WorklistRow(NamedTuple):

    label: str
    count: int
    url: str
    severity: str


class HealthCheck(NamedTuple):

    label: str
    ok: bool
    detail: str


class Registrant(NamedTuple):

    company: str
    acn: str
    registrant: str


def _changelist(app_label: str, model_name: str, query: str = "") -> str:
    return reverse(f"admin:{app_label}_{model_name}_changelist") + query


def worklist() -> list[WorklistRow]:
    cutoff = timezone.now() - PENDING_DEPLOYMENT_AGE
    return [
        WorklistRow(
            "Company applications waiting",
            Company.objects.awaiting_review().count(),
            _changelist("companies", "company", "?status__in=submitted,review,info_required"),
            SEVERITY_WARNING,
        ),
        WorklistRow(
            "Investor classifications awaiting verification",
            InvestorClassification.objects.submitted().count(),
            _changelist("users", "investorclassification", "?status__exact=submitted"),
            SEVERITY_WARNING,
        ),
        WorklistRow(
            "Offerings awaiting review",
            Offering.objects.awaiting_review().count(),
            _changelist("offerings", "offering", "?status__in=submitted,under_review"),
            SEVERITY_WARNING,
        ),
        WorklistRow(
            "Offerings at their cap and still open",
            Offering.objects.cap_reached().count(),
            _changelist("offerings", "offering", "?status__exact=approved"),
            SEVERITY_DANGER,
        ),
        WorklistRow(
            "Subscriptions awaiting payment",
            Subscription.objects.awaiting_payment().count(),
            _changelist("offerings", "subscription", "?status__exact=awaiting_payment"),
            SEVERITY_INFO,
        ),
        WorklistRow(
            "Subscriptions paid and not allotted",
            Subscription.objects.awaiting_allotment().count(),
            _changelist("offerings", "subscription", "?status__exact=paid"),
            SEVERITY_WARNING,
        ),
        WorklistRow(
            "Subscriptions whose mint is broadcast and unresolved",
            Subscription.objects.mint_unresolved().count(),
            _changelist("offerings", "subscription", "?status__exact=paid"),
            SEVERITY_DANGER,
        ),
        WorklistRow(
            "Whitelist entries pending",
            WhitelistEntry.objects.pending().count(),
            _changelist("whitelist", "whitelistentry", "?status__exact=pending"),
            SEVERITY_WARNING,
        ),
        WorklistRow(
            "Share issuance requests needing attention",
            ShareIssuanceRequest.objects.needing_attention().count(),
            _changelist("tokens", "shareissuancerequest", "?status__in=submitted,under_review,approved,failed"),
            SEVERITY_WARNING,
        ),
        WorklistRow(
            "Capital increase requests needing attention",
            CapitalIncreaseRequest.objects.needing_attention().count(),
            _changelist("tokens", "capitalincreaserequest", "?status__in=submitted,under_review,approved,failed"),
            SEVERITY_WARNING,
        ),
        WorklistRow(
            "Share tokens stuck deploying",
            ShareToken.objects.stuck_deploying(cutoff).count(),
            _changelist("tokens", "sharetoken", "?status__exact=deploying"),
            SEVERITY_DANGER,
        ),
        WorklistRow(
            "Allotments to an address with no whitelist entry",
            ShareIssuance.objects.without_whitelist_entry().values("recipient_address").distinct().count(),
            _changelist("whitelist", "whitelistentry"),
            SEVERITY_DANGER,
        ),
    ]


def _identity_check(operator: Operator) -> HealthCheck:
    missing = [field for field in OPERATOR_IDENTITY_FIELDS if not getattr(operator, field)]
    if missing:
        return HealthCheck("Operator row", False, OPERATOR_INCOMPLETE.format(fields=", ".join(missing)))
    return HealthCheck("Operator row", True, OPERATOR_COMPLETE)


def _setting_check(name: str) -> HealthCheck:
    if getattr(settings, name, ""):
        return HealthCheck(name, True, SETTING_PRESENT.format(name=name))
    return HealthCheck(name, False, SETTING_MISSING.format(name=name))


def _prefix_check(operator: Operator) -> HealthCheck:
    prefix = operator.payment_reference_prefix or ""
    if not prefix:
        return HealthCheck("Payment reference prefix", False, PREFIX_MISSING)
    if len(prefix) > MAX_PAYMENT_REFERENCE_PREFIX:
        return HealthCheck(
            "Payment reference prefix",
            False,
            PREFIX_TOO_LONG.format(prefix=prefix, length=len(prefix), maximum=MAX_PAYMENT_REFERENCE_PREFIX),
        )
    return HealthCheck("Payment reference prefix", True, PREFIX_OK.format(prefix=prefix))


def _settlement_check(operator: Operator) -> HealthCheck:
    assets = list(operator.supported_settlement_assets.all())
    if not assets:
        return HealthCheck("Settlement assets", False, NO_SETTLEMENT_ASSETS)
    chain = operator.receiving_wallet_chain
    undeployed = [asset.symbol for asset in assets if deployment_on_chain(asset, chain) is None]
    if undeployed:
        return HealthCheck(
            "Settlement assets", False, SETTLEMENT_NOT_DEPLOYED.format(symbols=", ".join(undeployed), chain=chain)
        )
    return HealthCheck("Settlement assets", True, SETTLEMENT_OK.format(count=len(assets), chain=chain))


def configuration_health() -> list[HealthCheck]:
    operator = Operator.get()
    return [
        _identity_check(operator),
        _setting_check("WHITELIST_CONTRACT_ADDRESS"),
        _setting_check("SHARE_TOKEN_FACTORY_ADDRESS"),
        _prefix_check(operator),
        _settlement_check(operator),
    ]


def registrants() -> list[Registrant]:
    keeper = Operator.get()
    name = keeper.legal_name or keeper.name
    return [
        Registrant(company.display_name, company.acn, name) for company in Company.objects.active().order_by("name")
    ]
