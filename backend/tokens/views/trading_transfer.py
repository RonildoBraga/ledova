from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from shared.views import AuthenticatedGenericViewSet
from tokens.serializers import BroadcastTransferSerializer, PrepareTransferSerializer
from tokens.serializers.trading_responses import (
    PreparedTokenTransferSerializer,
    TokenTransferReceiptSerializer,
)
from tokens.services import TokenTransferService
from tokens.services.signed_transactions import signer_of
from tokens.trading_wallet_access import resolve_verified_evm_wallets


class TradingTransferViewSet(AuthenticatedGenericViewSet):
    throttle_scope = "broadcast"

    @extend_schema(request=PrepareTransferSerializer, responses=PreparedTokenTransferSerializer)
    @action(detail=False, methods=["post"])
    def prepare(self, request):
        serializer = PrepareTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        authorized_wallets = resolve_verified_evm_wallets(request.user, [data["from_address"]])
        from_address = authorized_wallets.addresses[0]

        transfer_service = TokenTransferService()
        token = data["token"]

        tx_data = transfer_service.prepare_transfer(
            token=data["token"],
            from_address=from_address,
            to_address=data["to_address"],
            amount=data["amount"],
        )

        return Response(
            {
                "token": {
                    "uuid": str(token.uuid),
                    "symbol": token.symbol,
                    "contract_address": TokenTransferService.contract_address(token),
                },
                "from_address": from_address,
                "to_address": data["to_address"],
                "amount": data["amount"],
                "transaction_data": tx_data,
            }
        )

    @extend_schema(request=BroadcastTransferSerializer, responses=TokenTransferReceiptSerializer)
    @action(detail=False, methods=["post"])
    def broadcast(self, request):
        serializer = BroadcastTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        signed_transaction = data["signed_transaction"]
        resolve_verified_evm_wallets(request.user, [signer_of(signed_transaction)])

        transfer_service = TokenTransferService()
        tx_hash, receipt = transfer_service.broadcast_transfer(signed_transaction)

        return Response(
            {
                "tx_hash": tx_hash,
                "block_number": receipt.get("blockNumber"),
                "gas_used": receipt.get("gasUsed"),
            }
        )
