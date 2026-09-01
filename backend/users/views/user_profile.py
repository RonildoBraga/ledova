import logging
from datetime import datetime

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from authentication.models.user_token import UserToken
from portfolios.models import Portfolio
from shared.utils.logging_utils import LoggingContext
from shared.views.base import AuthenticatedModelViewSet
from users.filters import UserProfileFilter
from users.models import FinancialProfile, UserAccount, UserPreferences
from users.models.user_profile import UserProfile
from users.serializers import UserProfileSerializer
from wallets.models import Transaction, Wallet

logger = logging.getLogger("ledova_backend")


class UserProfileViewSet(AuthenticatedModelViewSet):
    serializer_class = UserProfileSerializer
    filterset_class = UserProfileFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "full_name"]

    def get_queryset(self):
        queryset = UserProfile.objects.visible_to_user(self.request.user).select_related("citizenship_country")
        if getattr(self, "action", None) in {"update", "partial_update"}:
            return queryset.select_for_update(of=("self",))
        return queryset

    def perform_create(self, serializer):
        logger.info(f"{LoggingContext.USER_PROFILE} Creating user profile")
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        logger.info(f"{LoggingContext.USER_PROFILE} Updating user profile")
        serializer.save()

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="delete-account")
    @transaction.atomic
    def delete_account(self, request):
        user = request.user
        logger.info(f"{LoggingContext.USER_PROFILE} Account deletion requested")

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        user.email = f"deleted_{user.id}_{timestamp}@deleted.invalid"
        user.is_active = False
        user.is_email_verified = False
        user.save()

        UserToken.objects.filter(user=user).delete()

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

        logger.info(f"{LoggingContext.USER_PROFILE} Account successfully deleted")

        return Response(
            {"message": "Your account has been successfully deleted."},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="export-data")
    def export_data(self, request):
        user = request.user
        logger.info(f"{LoggingContext.USER_PROFILE} Data export requested")

        export_data = {
            "exportedAt": datetime.now().isoformat(),
            "user": {
                "email": user.email,
                "dateJoined": user.date_joined.isoformat() if user.date_joined else None,
                "isEmailVerified": user.is_email_verified,
            },
            "profile": None,
            "preferences": None,
            "financialProfile": None,
            "accounts": [],
            "wallets": [],
            "transactions": [],
            "portfolios": [],
        }

        profile = None
        try:
            profile = UserProfile.objects.get(user=user)
            export_data["profile"] = {
                "fullName": profile.full_name,
                "dateOfBirth": profile.date_of_birth.isoformat() if profile.date_of_birth else None,
                "phoneCountryCode": profile.phone_country_code,
                "phoneNumber": profile.phone_number,
                "residentialAddress": profile.residential_address,
                "citizenshipCountry": profile.citizenship_country.name if profile.citizenship_country else None,
                "isIdVerified": profile.is_id_verified,
                "createdAt": profile.created_at.isoformat() if profile.created_at else None,
            }
        except UserProfile.DoesNotExist:
            pass

        if profile:
            accounts = UserAccount.objects.filter(user_profiles=profile)
            live_account_ids = set(accounts.values_list("pk", flat=True))

            try:
                preferences = UserPreferences.objects.get(user_profile=profile)
                export_data["preferences"] = {
                    "selectedPortfolio": (
                        str(preferences.selected_portfolio.uuid)
                        if preferences.selected_portfolio
                        and preferences.selected_portfolio.user_account_id in live_account_ids
                        else None
                    ),
                    "selectedAccount": (
                        str(preferences.selected_account.uuid)
                        if preferences.selected_account_id in live_account_ids
                        else None
                    ),
                }
            except UserPreferences.DoesNotExist:
                pass

            try:
                financial = FinancialProfile.objects.get(user_profile=profile)
                export_data["financialProfile"] = {
                    "occupation": financial.occupation,
                    "sourceOfFunds": financial.source_of_funds,
                    "sourceOfFundsOtherText": financial.source_of_funds_other_text,
                    "intendedUse": financial.intended_use,
                    "intendedUseOtherText": financial.intended_use_other_text,
                }
            except FinancialProfile.DoesNotExist:
                pass

            export_data["accounts"] = [
                {
                    "uuid": str(account.uuid),
                    "accountNumber": account.account_number,
                    "accountType": account.account_type,
                    "activationDate": account.activation_date.isoformat() if account.activation_date else None,
                    "createdAt": account.created_at.isoformat() if account.created_at else None,
                }
                for account in accounts
            ]

            wallets = Wallet.objects.filter(user_account__user_profiles=profile)
            export_data["wallets"] = [
                {
                    "uuid": str(wallet.uuid),
                    "name": wallet.name,
                    "chain": wallet.chain,
                    "address": wallet.address,
                    "nativeBalance": str(wallet.native_balance),
                    "marketValue": str(wallet.market_value),
                    "isVerified": wallet.is_verified,
                    "createdAt": wallet.created_at.isoformat() if wallet.created_at else None,
                }
                for wallet in wallets
            ]

            transactions = (
                Transaction.objects.filter(wallet__user_account__user_profiles=profile)
                .select_related("asset")
                .order_by("-block_timestamp")[:1000]
            )
            export_data["transactions"] = [
                {
                    "uuid": str(tx.uuid),
                    "txHash": tx.tx_hash,
                    "chain": tx.chain,
                    "status": tx.status,
                    "asset": tx.asset.symbol if tx.asset else None,
                    "amount": str(tx.amount) if tx.amount else "0",
                    "transactionFee": str(tx.transaction_fee) if tx.transaction_fee else None,
                    "fromAddress": tx.from_address,
                    "toAddress": tx.to_address,
                    "blockTimestamp": tx.block_timestamp.isoformat() if tx.block_timestamp else None,
                    "createdAt": tx.created_at.isoformat() if tx.created_at else None,
                }
                for tx in transactions
            ]

            portfolios = Portfolio.objects.filter(user_account__user_profiles=profile)
            export_data["portfolios"] = [
                {
                    "uuid": str(portfolio.uuid),
                    "name": portfolio.name,
                    "isActive": portfolio.is_active,
                    "createdAt": portfolio.created_at.isoformat() if portfolio.created_at else None,
                }
                for portfolio in portfolios
            ]

        logger.info(f"{LoggingContext.USER_PROFILE} Data export completed")

        return Response(export_data, status=status.HTTP_200_OK)
