from django.db.models import DecimalField, F, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce

from shared.constants import BLOCKCHAIN_BASE, BLOCKCHAIN_ETHEREUM
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED

_MONEY = DecimalField(max_digits=40, decimal_places=18)


class WalletQuerySet(QuerySet):
    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(user_account__user_profiles__user=user)

    def verified_evm(self):
        return self.filter(
            verification_status=WALLET_VERIFICATION_STATUS_VERIFIED,
            chain__in=(BLOCKCHAIN_ETHEREUM, BLOCKCHAIN_BASE),
        )

    def with_market_value(self):
        tradable = Q(holdings__asset__is_active=True, holdings__asset__is_verified=True)
        native = Q(holdings__asset__asset_type="native_crypto")
        holding_value = F("holdings__quantity") * F("holdings__asset__current_price")
        return self.annotate(
            annotated_market_value=Coalesce(Sum(holding_value, filter=tradable), Value(0), output_field=_MONEY),
            annotated_native_market_value=Coalesce(
                Sum(holding_value, filter=tradable & native), Value(0), output_field=_MONEY
            ),
            annotated_native_balance=Coalesce(
                Sum("holdings__quantity", filter=native & Q(holdings__asset__is_active=True)),
                Value(0),
                output_field=_MONEY,
            ),
        )

    def filter_by_address(self, address):
        return self.filter(address__iexact=address)

    def for_chain_with_l2_fallback(self, chain):
        from wallets.models.wallet import Blockchain

        verified = self.filter(verification_status=WALLET_VERIFICATION_STATUS_VERIFIED)
        wallet = verified.filter(chain=chain).order_by("-created_at").first()
        if not wallet and chain == Blockchain.BASE.value:
            wallet = verified.filter(chain=Blockchain.ETHEREUM.value).order_by("-created_at").first()
        return wallet
