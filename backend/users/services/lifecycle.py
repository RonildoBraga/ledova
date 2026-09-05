import logging
from datetime import datetime
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from authentication.email import normalize_email
from authentication.managers.user import EmailLookupState
from authentication.services import TokenService
from portfolios.models import Portfolio
from users.models import FinancialProfile, UserAccount, UserPreferences, UserProfile
from wallets.models import Transaction, Wallet

logger = logging.getLogger(__name__)


@transaction.atomic
def delete_account(user):
    logger.info("Account deletion requested")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    tombstone = normalize_email(f"deleted_{user.id}_{timestamp}_{uuid4().hex}@deleted.invalid")
    if user.__class__.objects.resolve_email(tombstone).state is not EmailLookupState.ABSENT:
        raise serializers.ValidationError({"error": ["Account deletion could not be completed."]})
    user.email = tombstone
    user.is_active = False
    user.is_email_verified = False
    user.save(update_fields=["email", "is_active", "is_email_verified"])

    TokenService.revoke_all(user)

    try:
        profile = UserProfile.objects.get(user=user)
        profile.full_name = "Deleted User"
        profile.phone_country_code = None
        profile.phone_number = None
        profile.residential_address = None
        profile.date_of_birth = None
        profile.save()
    except UserProfile.DoesNotExist:
        pass

    logger.info("Account successfully deleted")


def export_account_data(user):
    logger.info("Data export requested")

    data = {
        "exported_at": timezone.now(),
        "user": {
            "email": user.email,
            "date_joined": user.date_joined,
            "is_email_verified": user.is_email_verified,
        },
        "profile": None,
        "preferences": None,
        "financial_profile": None,
        "accounts": [],
        "wallets": [],
        "transactions": [],
        "portfolios": [],
    }

    profile = getattr(user, "userprofile", None)
    if profile is None:
        return data

    data["profile"] = {
        "full_name": profile.full_name,
        "date_of_birth": profile.date_of_birth,
        "phone_country_code": profile.phone_country_code,
        "phone_number": profile.phone_number,
        "residential_address": profile.residential_address,
        "citizenship_country": profile.citizenship_country.name if profile.citizenship_country else None,
        "is_id_verified": profile.is_id_verified,
        "created_at": profile.created_at,
    }

    accounts = UserAccount.objects.filter(user_profiles=profile)
    live_account_ids = set(accounts.values_list("pk", flat=True))

    preferences = UserPreferences.objects.filter(user_profile=profile).select_related("selected_portfolio").first()
    if preferences is not None:
        portfolio = preferences.selected_portfolio
        data["preferences"] = {
            "selected_portfolio": (
                portfolio.uuid if portfolio and portfolio.user_account_id in live_account_ids else None
            ),
            "selected_account": (
                preferences.selected_account.uuid if preferences.selected_account_id in live_account_ids else None
            ),
        }

    data["financial_profile"] = (
        FinancialProfile.objects.filter(user_profile=profile)
        .values(
            "occupation", "source_of_funds", "source_of_funds_other_text", "intended_use", "intended_use_other_text"
        )
        .first()
    )
    data["accounts"] = list(accounts.values("uuid", "account_number", "account_type", "activation_date", "created_at"))
    data["wallets"] = [
        {
            "uuid": wallet.uuid,
            "name": wallet.name,
            "chain": wallet.chain,
            "address": wallet.address,
            "native_balance": str(wallet.annotated_native_balance),
            "market_value": str(wallet.annotated_market_value),
            "is_verified": wallet.is_verified,
            "created_at": wallet.created_at,
        }
        for wallet in Wallet.objects.filter(user_account__in=accounts).with_market_value()
    ]
    transactions = (
        Transaction.objects.filter(wallet__user_account__in=accounts)
        .select_related("asset")
        .order_by("-block_timestamp")[:1000]
    )
    data["transactions"] = [
        {
            "uuid": tx.uuid,
            "tx_hash": tx.tx_hash,
            "chain": tx.chain,
            "status": tx.status,
            "asset": tx.asset.symbol if tx.asset else None,
            "amount": str(tx.amount or 0),
            "transaction_fee": str(tx.transaction_fee) if tx.transaction_fee else None,
            "from_address": tx.from_address,
            "to_address": tx.to_address,
            "block_timestamp": tx.block_timestamp,
            "created_at": tx.created_at,
        }
        for tx in transactions
    ]
    data["portfolios"] = list(
        Portfolio.objects.filter(user_account__in=accounts).values("uuid", "name", "is_active", "created_at")
    )

    logger.info("Data export completed")
    return data
