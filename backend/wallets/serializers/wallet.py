from django.conf import settings
from rest_framework import serializers
from web3 import Web3

from integrations.blockchain.bitcoin import is_bitcoin_address_valid
from shared.constants import (
    BLOCKCHAIN_BASE,
    BLOCKCHAIN_BITCOIN,
    BLOCKCHAIN_ETHEREUM,
    SUPPORTED_CHAINS,
)
from users.models import UserAccount
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.models import Wallet


class WalletSerializer(serializers.ModelSerializer):
    uuid = serializers.CharField(read_only=True)
    user_account = serializers.PrimaryKeyRelatedField(queryset=UserAccount.objects.none())
    chain = serializers.ChoiceField(choices=sorted(SUPPORTED_CHAINS))

    native_balance = serializers.DecimalField(
        source="annotated_native_balance", read_only=True, max_digits=40, decimal_places=18
    )
    native_market_value = serializers.DecimalField(
        source="annotated_native_market_value", read_only=True, max_digits=40, decimal_places=18
    )
    market_value = serializers.DecimalField(
        source="annotated_market_value", read_only=True, max_digits=40, decimal_places=18
    )

    class Meta:
        model = Wallet
        fields = (
            "uuid",
            "user_account",
            "name",
            "address",
            "chain",
            "wallet_type",
            "native_balance",
            "native_market_value",
            "market_value",
            "verification_status",
            "verification_challenge",
            "verification_signature",
            "verified_at",
            "last_synced_at",
            "derivation_path",
            "master_fingerprint",
            "address_index",
            "parent_public_key",
            "parent_chain_code",
            "parent_derivation_path",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "verification_status",
            "verification_challenge",
            "verification_signature",
            "verified_at",
            "last_synced_at",
            "created_at",
            "updated_at",
        )

    def get_fields(self):
        fields = super().get_fields()

        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            fields["user_account"].queryset = UserAccount.objects.visible_to_user(request.user)
        else:
            fields["user_account"].queryset = UserAccount.objects.none()
        return fields

    def validate_address(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Wallet address cannot be empty.")

        value = value.strip()

        if len(value) < 25 or len(value) > 70:
            raise serializers.ValidationError("Wallet address length is invalid.")

        return value

    @staticmethod
    def _verified_identity_change_errors(instance, data):
        if not instance or instance.verification_status != WALLET_VERIFICATION_STATUS_VERIFIED:
            return {}

        immutable_changes = {}
        for field in ("address", "chain", "user_account"):
            if field not in data:
                continue
            current = getattr(instance, field)
            proposed = data[field]
            current_value = current.pk if field == "user_account" else current
            proposed_value = proposed.pk if field == "user_account" else proposed
            if proposed_value != current_value:
                immutable_changes[field] = "Verified wallet identity cannot be changed."
        return immutable_changes

    def validate(self, data):
        immutable_changes = self._verified_identity_change_errors(self.instance, data)
        if immutable_changes:
            raise serializers.ValidationError(immutable_changes)

        address = data.get("address", getattr(self.instance, "address", None))
        chain = data.get("chain", getattr(self.instance, "chain", None))
        user_account = data.get("user_account", getattr(self.instance, "user_account", None))

        if address and chain in (BLOCKCHAIN_ETHEREUM, BLOCKCHAIN_BASE) and not Web3.is_address(address):
            raise serializers.ValidationError({"address": "Enter a valid EVM address."})
        if address and chain == BLOCKCHAIN_BITCOIN and not is_bitcoin_address_valid(address, settings.BITCOIN_NETWORK):
            raise serializers.ValidationError({"address": "Enter an address for the configured Bitcoin test network."})

        if address and user_account:
            duplicate_wallets = Wallet.objects.filter(address=address, user_account=user_account)
            if self.instance:
                duplicate_wallets = duplicate_wallets.exclude(pk=self.instance.pk)
            if duplicate_wallets.exists():
                raise serializers.ValidationError(
                    {"address": "This wallet address has already been added to your account."}
                )

        return data
