import logging

from django.db import transaction

from compliance.services.risk_assessment import RiskAssessmentService
from portfolios.models import Portfolio
from shared.utils.logging_utils import LoggingContext
from users.models import UserAccount, UserPreferences, UserProfile

logger = logging.getLogger("ledova_backend")


@transaction.atomic
def ensure_defaults(user):
    """Give a signing-up user a profile, one account, one portfolio and preferences pointing at them.
    Idempotent: existing rows are reused and only missing selections are filled in."""
    profile, _ = UserProfile.objects.get_or_create(user=user)

    account = profile.user_accounts.first()
    if account is None:
        account = UserAccount.objects.create(account_number=f"ACC-{user.id:06d}", director=profile)
        account.user_profiles.add(profile)
        RiskAssessmentService.create_pending_assessment(user_account=account)
        logger.info(f"{LoggingContext.USER_SIGNUP} Created account {account.uuid} for {user.email}")

    portfolio = account.portfolios.first()
    if portfolio is None:
        portfolio = Portfolio.objects.create(user_account=account, name="My Portfolio")
        logger.info(f"{LoggingContext.USER_SIGNUP} Created portfolio {portfolio.uuid} for {user.email}")

    preferences, created = UserPreferences.objects.get_or_create(
        user_profile=profile,
        defaults={"selected_account": account, "selected_portfolio": portfolio},
    )
    if not created and (preferences.selected_account_id is None or preferences.selected_portfolio_id is None):
        preferences.selected_account = account
        preferences.selected_portfolio = portfolio
        preferences.save(update_fields=["selected_account", "selected_portfolio"])

    logger.info(
        f"{LoggingContext.USER_SIGNUP} Defaults ready for {user.email}: "
        f"Account {account.uuid}, Portfolio {portfolio.uuid}"
    )
    return profile, account, portfolio, preferences
