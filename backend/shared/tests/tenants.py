from datetime import date, timedelta
from decimal import Decimal
from itertools import count
from types import SimpleNamespace
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone
from eth_account import Account
from eth_utils import to_checksum_address

from assets.models import Asset, AssetChainDeployment
from companies.models import (
    Company,
    CompanyDocument,
    CompanyStatus,
    CompanyType,
    DocumentType,
)
from companies.validators import acn_check_digit
from documents.models import Document
from offerings.models import Offering, OfferingExemption, Subscription
from portfolios.models import Portfolio
from shared.constants import BLOCKCHAIN_BASE
from shared.models import Country
from tokens.models import (
    CapitalIncreaseRequest,
    ShareToken,
    ShareTokenStatus,
    SwapOrder,
    TransferOrder,
)
from tokens.models.choices import TransferOrderType
from users.constants import ACCOUNT_STATUS_ACTIVE
from users.models import (
    DeviceToken,
    FavouriteAsset,
    FinancialProfile,
    InvestorCategory,
    InvestorClassification,
    InvestorClassificationStatus,
    Notification,
    NotificationPreferences,
    UserAccount,
    UserPreferences,
    UserProfile,
)
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.models import Holding, HoldingSnapshot, Transaction, Wallet

User = get_user_model()
PASSWORD = "pw-12345678"
SHARED_KEYS = ("asset", "spare_asset", "stablecoin", "country")
PHANTOM_WALLET_ADDRESS = "0x" + "d" * 40
_sequence = count(1)


def _hex40(prefix, number):
    return "0x" + prefix + f"{number:039x}"


def _wallet_key(number):
    return Account.from_key("0x" + f"{number:064x}")


def _signed_native_transfer(key, recipient):
    return key.sign_transaction(
        {
            "nonce": 0,
            "to": recipient,
            "value": 1,
            "gas": 21000,
            "gasPrice": 10**9,
            "chainId": settings.BLOCKCHAIN_CHAIN_ID,
        }
    ).raw_transaction.to_0x_hex()


def reference_data():
    asset, _ = Asset.objects.get_or_create(
        symbol="TENANT",
        defaults={
            "name": "Tenant asset",
            "asset_type": "tokenized_security",
            "is_active": True,
            "is_verified": True,
            "current_price": Decimal("2"),
        },
    )
    spare_asset, _ = Asset.objects.get_or_create(
        symbol="TENANT2",
        defaults={
            "name": "Tenant spare asset",
            "asset_type": "tokenized_security",
            "is_active": True,
            "is_verified": True,
        },
    )
    stablecoin, _ = Asset.objects.get_or_create(
        symbol="TUSD",
        defaults={
            "name": "Tenant dollar",
            "asset_type": "stablecoin",
            "decimals": 2,
            "is_active": True,
            "is_verified": True,
        },
    )
    AssetChainDeployment.objects.get_or_create(
        asset=stablecoin,
        chain="base",
        defaults={"contract_address": "0x" + "5" * 40, "decimals": 2},
    )
    country, _ = Country.objects.get_or_create(code="TST", defaults={"name": "Tenant country", "is_available": True})
    return SimpleNamespace(asset=asset, spare_asset=spare_asset, stablecoin=stablecoin, country=country)


def an_acn(number: int) -> str:
    base = f"{number:08d}"
    return base + str(acn_check_digit(base))


def make_tenant(label, *, staff=False, superuser=False):
    number = next(_sequence)
    refs = reference_data()
    email = f"{label}@tenants.example.test"
    if superuser:
        user = User.objects.create_superuser(email=email, password=PASSWORD)
    else:
        user = User.objects.create_user(
            email=email, password=PASSWORD, is_staff=staff, is_active=True, is_email_verified=True
        )
    profile = UserProfile.objects.create(user=user, full_name=f"{label} owner", citizenship_country=refs.country)
    financial_profile = FinancialProfile.objects.create(user_profile=profile, occupation=f"{label} occupation")
    account = UserAccount.objects.create(account_number=f"ACCT-{label.upper()}"[:20], director=profile)
    account.user_profiles.add(profile)

    wallet_key = _wallet_key(number)
    wallet = Wallet.objects.create(
        user_account=account,
        address=wallet_key.address,
        chain="base",
        verification_status=WALLET_VERIFICATION_STATUS_VERIFIED,
        verification_challenge=f"challenge-{label}",
        verified_at=timezone.now(),
    )
    spare_wallet = Wallet.objects.create(user_account=account, address=_hex40("b", number), chain="ethereum")
    holding = Holding.objects.create(wallet=wallet, asset=refs.asset, quantity=Decimal("5"))
    transaction = Transaction.objects.create(
        tx_hash=f"0x{label}",
        chain="base",
        from_address=wallet.address,
        to_address=_hex40("f", number),
        asset=refs.asset,
        amount=Decimal("1"),
        wallet=wallet,
    )
    holding_snapshot = HoldingSnapshot.objects.create(
        holding=holding,
        quantity=Decimal("5"),
        snapshot_date=date(2026, 9, 1),
        snapshot_reason="DAILY",
        caused_by_transaction=transaction,
    )

    portfolio = Portfolio.objects.create(user_account=account, name=f"{label} portfolio")
    portfolio.wallets.add(wallet)
    preferences = UserPreferences.objects.create(
        user_profile=profile, selected_account=account, selected_portfolio=portfolio
    )
    favourite = FavouriteAsset.objects.create(user_account=account, asset=refs.asset)
    device_token = DeviceToken.objects.create(user=user, push_token=f"ExponentPushToken[{label}]", device_type="ios")
    notification = Notification.objects.create(user=user, title=f"For {label}", body="Body")
    notification_preferences = NotificationPreferences.objects.create(user_profile=profile)
    investor_classification = InvestorClassification.objects.create(
        user_account=account,
        category=InvestorCategory.PROFESSIONAL_INVESTOR,
        declaration_accepted=True,
        declaration_text="Declared",
        declared_basis=f"{label} basis",
        evidence_file_size=len(label),
        evidence_mime_type="application/pdf",
        submitted_at=timezone.now(),
    )
    investor_classification.evidence_file.save(
        f"{label}-evidence.pdf", ContentFile(f"evidence for {label}".encode()), save=True
    )

    company = Company.objects.create(
        owner=user,
        name=f"{label} Pty Ltd",
        company_type=CompanyType.PROPRIETARY,
        acn=an_acn(number),
        operator_wallet=wallet,
    )
    company_document = CompanyDocument.objects.create(
        company=company,
        document_type=DocumentType.ASIC_EXTRACT,
        name=f"{label} ASIC extract",
        external_url=f"https://docs.example.test/{label}",
        file_size=1,
        mime_type="application/pdf",
    )
    company_document.file.save(
        f"{label}-asic-extract.pdf", ContentFile(f"asic extract for {label}".encode()), save=True
    )
    token = ShareToken.objects.create(company=company, name=f"{label} draft shares", symbol="DRF", total_supply="1000")
    deployed_token = ShareToken.objects.create(
        company=company,
        name=f"{label} shares",
        symbol="DEP",
        total_supply="1000",
        status=ShareTokenStatus.DEPLOYED,
        contract_address=_hex40("c", number),
        chain=BLOCKCHAIN_BASE,
    )
    capital_increase = CapitalIncreaseRequest.objects.create(
        token=deployed_token,
        additional_shares=100,
        new_authorized_total=1100,
        purpose="Growth",
        board_resolution_reference=f"BOARD-{label}",
    )
    order_fields = {
        "token": deployed_token,
        "payment_asset": refs.stablecoin,
        "wallet": wallet,
        "owner_account": account,
        "wallet_address": wallet.address,
        "quantity": 10,
        "price_per_share": Decimal("1.50"),
    }
    order = TransferOrder.objects.create(order_type=TransferOrderType.SELL, **order_fields)
    counter_order = TransferOrder.objects.create(order_type=TransferOrderType.BUY, **order_fields)
    swap = SwapOrder.objects.create(
        sell_order=order,
        buy_order=counter_order,
        share_token=deployed_token,
        payment_asset=refs.stablecoin,
        seller_address=wallet.address,
        buyer_address=wallet.address,
        share_amount=10,
        payment_amount=1500,
        nonce=number,
        order_hash="0x" + f"{number:064x}",
    )
    offering = Offering.objects.create(
        token=deployed_token,
        exemption=OfferingExemption.PROFESSIONAL,
        price_per_share=Decimal("2.50"),
        minimum_shares=10,
        target_shares=50,
        cap_shares=100,
        opens_at=timezone.now() + timedelta(days=1),
        closes_at=timezone.now() + timedelta(days=30),
        summary=f"{label} offering",
    )
    subscription = Subscription.objects.create(
        offering=offering,
        user_account=account,
        wallet=wallet,
        submitted_by=user,
        quantity=10,
        price_per_share=Decimal("2.50"),
        amount_due=Decimal("25.00"),
    )
    document = Document.objects.create(
        uploaded_by=user,
        document_type="payslip",
        original_filename=f"{label}.pdf",
        mime_type="application/pdf",
    )
    document.file.save(f"{label}-payslip.pdf", ContentFile(f"payslip for {label}".encode()), save=True)
    return SimpleNamespace(
        label=label,
        refs=refs,
        user=user,
        profile=profile,
        financial_profile=financial_profile,
        account=account,
        wallet=wallet,
        signed_transfer=_signed_native_transfer(wallet_key, to_checksum_address(_hex40("9", number))),
        spare_wallet=spare_wallet,
        holding=holding,
        transaction=transaction,
        holding_snapshot=holding_snapshot,
        portfolio=portfolio,
        preferences=preferences,
        favourite=favourite,
        device_token=device_token,
        notification=notification,
        notification_preferences=notification_preferences,
        investor_classification=investor_classification,
        company=company,
        company_document=company_document,
        token=token,
        deployed_token=deployed_token,
        capital_increase=capital_increase,
        offering=offering,
        subscription=subscription,
        order=order,
        counter_order=counter_order,
        swap=swap,
        document=document,
    )


def make_eligible(tenant):
    UserProfile.objects.filter(pk=tenant.profile.pk).update(is_id_verified=True)
    UserAccount.objects.filter(pk=tenant.account.pk).update(account_status=ACCOUNT_STATUS_ACTIVE)
    InvestorClassification.objects.filter(pk=tenant.investor_classification.pk).update(
        status=InvestorClassificationStatus.VERIFIED, expires_at=timezone.now() + timedelta(days=365)
    )


def make_associated(tenant, company):
    UserProfile.objects.filter(pk=tenant.profile.pk).update(is_id_verified=True)
    UserAccount.objects.filter(pk=tenant.account.pk).update(account_status=ACCOUNT_STATUS_ACTIVE)
    return InvestorClassification.objects.create(
        user_account=tenant.account,
        company=company,
        category=InvestorCategory.ASSOCIATED_PERSON,
        status=InvestorClassificationStatus.VERIFIED,
        expires_at=timezone.now() + timedelta(days=365),
        declaration_accepted=True,
        declaration_text="Declared",
        declared_basis=f"{tenant.label} association",
        evidence_file_size=len(tenant.label),
        evidence_mime_type="application/pdf",
        submitted_at=timezone.now(),
    )


def open_to_investors(tenant):
    Company.objects.filter(pk=tenant.company.pk).update(status=CompanyStatus.ACTIVE, is_open_to_investors=True)


def _rows(tenant):
    return {name: value for name, value in vars(tenant).items() if isinstance(value, models.Model)}


def route_context(tenant):
    context = {name: str(row.uuid) for name, row in _rows(tenant).items() if hasattr(row, "uuid")}
    context.update(
        series_point=f"{tenant.portfolio.uuid}:{tenant.holding_snapshot.snapshot_date.isoformat()}",
        wallet_address=tenant.wallet.address,
        signed_transfer=tenant.signed_transfer,
        push_token=tenant.device_token.push_token,
        acn=tenant.company.acn,
        asset=str(tenant.refs.asset.uuid),
        spare_asset=str(tenant.refs.spare_asset.uuid),
        stablecoin=str(tenant.refs.stablecoin.uuid),
        country=str(tenant.refs.country.uuid),
    )
    return context


def phantom_context(tenant):
    context = {key: value if key in SHARED_KEYS else str(uuid4()) for key, value in route_context(tenant).items()}
    context["wallet_address"] = PHANTOM_WALLET_ADDRESS
    return context


def snapshot(tenant):
    rows = {}
    for name, row in _rows(tenant).items():
        fresh = type(row).objects.get(pk=row.pk)
        rows[name] = {field.attname: getattr(fresh, field.attname) for field in fresh._meta.concrete_fields}
    rows["portfolio_wallets"] = sorted(tenant.portfolio.wallets.values_list("uuid", flat=True))
    rows["account_profiles"] = sorted(tenant.account.user_profiles.values_list("pk", flat=True))
    counts = {type(row)._meta.label: type(row).objects.count() for row in _rows(tenant).values()}
    return rows, counts
