from decimal import Decimal

from rest_framework import serializers

from wallets.services.signed_transfers import plan_signed_transfer

AMOUNT_DIGITS = {"max_digits": 30, "decimal_places": 18, "min_value": Decimal("0")}


class BroadcastTransferSerializer(serializers.Serializer):
    signed_transaction = serializers.CharField()
    to_address = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    amount = serializers.DecimalField(required=False, allow_null=True, **AMOUNT_DIGITS)
    transaction_fee = serializers.DecimalField(required=False, allow_null=True, **AMOUNT_DIGITS)
    token_contract = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def validate(self, data):
        plan = plan_signed_transfer(
            self.context["wallet"],
            data["signed_transaction"],
            data.get("token_contract"),
        )

        if plan is None:
            return data

        data["to_address"] = plan.to_address
        data["amount"] = plan.amount
        data["token_contract"] = plan.token_contract
        return data
