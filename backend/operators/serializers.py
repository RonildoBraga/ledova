from rest_framework import serializers

from assets.models import Asset
from assets.serializers.asset import AssetChainDeploymentSerializer
from operators.models import Operator

PAYMENT_FIELDS = (
    "bank_account_name",
    "bank_bsb",
    "bank_account_number",
    "payment_reference_prefix",
    "receiving_wallet_address",
)


class SettlementAssetSerializer(serializers.ModelSerializer):
    chain_deployments = AssetChainDeploymentSerializer(many=True, read_only=True)

    class Meta:
        model = Asset
        fields = ["uuid", "symbol", "name", "chain_deployments"]
        read_only_fields = fields


class OperatorSerializer(serializers.ModelSerializer):
    """The public operator profile; payment_instructions carries only the rails the operator has filled in."""

    supported_settlement_assets = SettlementAssetSerializer(many=True, read_only=True)
    issued_stablecoin = SettlementAssetSerializer(read_only=True, allow_null=True)
    payment_instructions = serializers.SerializerMethodField()

    class Meta:
        model = Operator
        fields = [
            "name",
            "legal_name",
            "abn",
            "contact_email",
            "website",
            "deployment_mode",
            "supported_settlement_assets",
            "issued_stablecoin",
            "investor_kyc_required",
            "issuer_kyc_required",
            "payment_instructions",
        ]
        read_only_fields = fields

    def get_payment_instructions(self, operator):
        instructions = {field: getattr(operator, field) for field in PAYMENT_FIELDS if getattr(operator, field)}
        if operator.receiving_wallet_address:
            instructions["receiving_wallet_chain"] = operator.receiving_wallet_chain
        return instructions
