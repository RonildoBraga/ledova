from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from offerings.models import Offering, OfferingStatus, Subscription, SubscriptionStatus
from offerings.services.subscription import create_draft
from operators.models import Operator
from shared.tests.tenants import make_eligible
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.models import Wallet
from whitelist.models import WhitelistEntry

BANK = {
    "bank_account_name": "Ledova Trust Account",
    "bank_bsb": "062000",
    "bank_account_number": "12345678",
    "payment_reference_prefix": "PAY",
    "receiving_wallet_address": "0x" + "d" * 40,
}


def forget_fixture_subscriptions():
    Subscription.objects.all().delete()


def configure_operator(stablecoin=None, **overrides):
    operator = Operator.get()
    for field, value in {**BANK, **overrides}.items():
        setattr(operator, field, value)
    operator.save()
    if stablecoin is not None:
        operator.supported_settlement_assets.add(stablecoin)
    return operator


def open_offering(tenant, stablecoin=None, **overrides):
    Offering.objects.filter(pk=tenant.offering.pk).update(
        status=OfferingStatus.APPROVED, opens_at=timezone.now() - timedelta(days=1), **overrides
    )
    tenant.offering.refresh_from_db()
    if stablecoin is not None:
        tenant.offering.settlement_assets.add(stablecoin)
    return tenant.offering


def eligible_subscriber(tenant):
    make_eligible(tenant)
    tenant.account.refresh_from_db()
    return tenant.account


def draft_subscription(tenant, quantity=10, offering=None, wallet=None, account=None):
    return create_draft(
        offering or tenant.offering,
        account or tenant.account,
        wallet or tenant.wallet,
        quantity,
        submitted_by=tenant.user,
    )


def paid_subscription(tenant, quantity=10, allotted=None, wallet=None):
    subscription = draft_subscription(tenant, quantity=quantity, wallet=wallet)
    Subscription.objects.filter(pk=subscription.pk).update(
        status=SubscriptionStatus.PAID,
        amount_received=Decimal(quantity) * subscription.price_per_share,
        payment_received_on=timezone.now().date(),
        allotted_quantity=allotted,
        reference=f"PAY{str(subscription.uuid).replace('-', '')[:8].upper()}",
    )
    subscription.refresh_from_db()
    return subscription


def extra_wallet(tenant, suffix):
    wallet = Wallet.objects.create(
        user_account=tenant.account,
        address="0x" + suffix * 40,
        chain="base",
        verification_status=WALLET_VERIFICATION_STATUS_VERIFIED,
        verified_at=timezone.now(),
    )
    WhitelistEntry.objects.create(wallet=wallet, is_whitelisted=True)
    return wallet
