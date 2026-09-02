import logging

from django.db import transaction

from compliance.services.risk_assessment import RiskAssessmentService
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


class UserSetupService:
    @staticmethod
    @transaction.atomic
    def ensure_defaults(user):
        from portfolios.models import Portfolio
        from users.models import UserAccount, UserPreferences, UserProfile

        user_profile, _ = UserProfile.objects.get_or_create(user=user)

        existing_account = user_profile.user_accounts.first()
        if existing_account and existing_account.portfolios.exists():
            account = existing_account
            portfolio = account.portfolios.first()

            user_preferences, created = UserPreferences.objects.get_or_create(
                user_profile=user_profile,
                defaults={
                    "selected_account": account,
                    "selected_portfolio": portfolio,
                },
            )

            if not created and (not user_preferences.selected_account or not user_preferences.selected_portfolio):
                user_preferences.selected_account = account
                user_preferences.selected_portfolio = portfolio
                user_preferences.save()

            logger.info(
                f"{LoggingContext.USER_SIGNUP} Verified existing defaults for {user.email}: "
                f"Account {account.uuid}, Portfolio {portfolio.uuid}"
            )
            return user_profile, account, portfolio, user_preferences

        if existing_account:
            account = existing_account
        else:
            account = UserAccount.objects.create(account_number=f"ACC-{user.id:06d}", director=user_profile)
            account.user_profiles.add(user_profile)
            RiskAssessmentService.create_pending_assessment(user_account=account)
            logger.info(f"{LoggingContext.USER_SIGNUP} Created account {account.uuid} for {user.email}")

        portfolio = Portfolio.objects.create(user_account=account, name="My Portfolio")
        logger.info(f"{LoggingContext.USER_SIGNUP} Created portfolio {portfolio.uuid} for {user.email}")

        user_preferences, created = UserPreferences.objects.get_or_create(
            user_profile=user_profile,
            defaults={
                "selected_account": account,
                "selected_portfolio": portfolio,
            },
        )

        if not created:
            user_preferences.selected_account = account
            user_preferences.selected_portfolio = portfolio
            user_preferences.save()

        logger.info(
            f"{LoggingContext.USER_SIGNUP} Created defaults for {user.email}: "
            f"Account {account.uuid}, Portfolio {portfolio.uuid}"
        )

        return user_profile, account, portfolio, user_preferences
