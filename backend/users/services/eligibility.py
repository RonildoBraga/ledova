from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple

from operators.models import Operator
from users.constants import (
    ACCOUNT_STATUS_PENDING,
    ACCOUNT_STATUS_REJECTED,
    ACCOUNT_STATUS_SUSPENDED,
    ACCOUNT_STATUS_TERMINATED,
)
from users.exceptions import InvestorNotEligibleException
from users.models.investor_classification import (
    PRODUCT_VALUE_THRESHOLD_AUD,
    InvestorCategory,
    InvestorClassification,
)
from users.models.user_account import UserAccount

NO_INVESTOR_ACCOUNT = "no_investor_account"
ACCOUNT_NOT_IN_GOOD_STANDING = "account_not_in_good_standing"
IDENTITY_NOT_VERIFIED = "identity_not_verified"
NO_LIVE_CLASSIFICATION = "no_live_classification"
AMOUNT_BELOW_PRODUCT_VALUE_THRESHOLD = "amount_below_product_value_threshold"

REFUSED_ACCOUNT_STATUSES = (ACCOUNT_STATUS_REJECTED, ACCOUNT_STATUS_SUSPENDED, ACCOUNT_STATUS_TERMINATED)


@dataclass(frozen=True)
class InvestorEligibility:
    is_eligible: bool
    account: Optional[UserAccount]
    classification: Optional[InvestorClassification]
    reasons: Tuple[str, ...]


def _standing_refused(account, investor_kyc_required):
    if account.account_status in REFUSED_ACCOUNT_STATUSES:
        return True
    return investor_kyc_required and account.account_status == ACCOUNT_STATUS_PENDING


def _every_holder_verified(account):
    profiles = account.user_profiles.all()
    return profiles.exists() and not profiles.filter(is_id_verified=False).exists()


def _evaluate(account, investor_kyc_required, company):
    reasons = []
    if _standing_refused(account, investor_kyc_required):
        reasons.append(ACCOUNT_NOT_IN_GOOD_STANDING)
    if investor_kyc_required and not _every_holder_verified(account):
        reasons.append(IDENTITY_NOT_VERIFIED)

    classification = InvestorClassification.objects.filter(user_account=account).live().for_company(company).first()
    if classification is None:
        reasons.append(NO_LIVE_CLASSIFICATION)

    return InvestorEligibility(
        is_eligible=not reasons,
        account=account,
        classification=classification,
        reasons=tuple(reasons),
    )


def investor_eligibility(user, company=None) -> InvestorEligibility:
    accounts = list(UserAccount.objects.visible_to_user(user).investing().order_by("created_at"))
    if not accounts:
        return InvestorEligibility(is_eligible=False, account=None, classification=None, reasons=(NO_INVESTOR_ACCOUNT,))

    investor_kyc_required = Operator.get().investor_kyc_required
    outcomes = [_evaluate(account, investor_kyc_required, company) for account in accounts]
    for outcome in outcomes:
        if outcome.is_eligible:
            return outcome
    return outcomes[0]


def require_investor_eligibility(user, company=None) -> InvestorEligibility:
    outcome = investor_eligibility(user, company)
    if not outcome.is_eligible:
        raise InvestorNotEligibleException(outcome.reasons)
    return outcome


def require_subscription_eligibility(user, company, amount_aud: Decimal) -> InvestorEligibility:
    outcome = require_investor_eligibility(user, company)
    if outcome.classification.category == InvestorCategory.PRODUCT_VALUE:
        if Decimal(amount_aud) < PRODUCT_VALUE_THRESHOLD_AUD:
            raise InvestorNotEligibleException((AMOUNT_BELOW_PRODUCT_VALUE_THRESHOLD,))
    return outcome
