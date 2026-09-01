from django.db.models import DecimalField, F, QuerySet, Sum, Value
from django.db.models.functions import Coalesce


class WalletQuerySet(QuerySet):
    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(user_account__user_profiles__user=user)

    def with_optimized_data(self):
        return self.select_related("user_account", "user_account__user_profile")

    def with_market_value(self):
        from django.db.models import Q

        return self.annotate(
            annotated_market_value=Coalesce(
                Sum(
                    F("holdings__quantity") * F("holdings__asset__current_price"),
                    filter=Q(holdings__asset__is_active=True, holdings__asset__is_verified=True),
                ),
                Value(0),
                output_field=DecimalField(max_digits=40, decimal_places=18),
            ),
            annotated_native_market_value=Coalesce(
                Sum(
                    F("holdings__quantity") * F("holdings__asset__current_price"),
                    filter=Q(
                        holdings__asset__is_active=True,
                        holdings__asset__is_verified=True,
                        holdings__asset__asset_type="native_crypto",
                    ),
                ),
                Value(0),
                output_field=DecimalField(max_digits=40, decimal_places=18),
            ),
        )

    def verified(self):
        return self.filter(verification_status="VERIFIED")

    def pending_verification(self):
        return self.filter(verification_status="PENDING")

    def filter_by_address(self, address):
        return self.filter(address__iexact=address)

    def by_chain(self, chain):
        if chain:
            return self.filter(chain__iexact=chain)
        return self

    def for_chain_with_l2_fallback(self, chain):
        from wallets.models.wallet import Blockchain

        wallet = self.filter(chain=chain).order_by("-created_at").first()
        if not wallet and chain == Blockchain.BASE.value:
            wallet = self.filter(chain=Blockchain.ETHEREUM.value).order_by("-created_at").first()
        return wallet
