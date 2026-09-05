from rest_framework.decorators import action
from rest_framework.response import Response

from shared.views import AuthenticatedGenericViewSet
from tokens.serializers import BroadcastTransferSerializer, PrepareTransferSerializer
from tokens.services import TransferService
from tokens.trading_wallet_access import resolve_verified_evm_wallets


class TradingTransferViewSet(AuthenticatedGenericViewSet):
    throttle_scope = "broadcast"

    @action(detail=False, methods=["post"])
    def prepare(self, request):
        serializer = PrepareTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        authorized_wallets = resolve_verified_evm_wallets(request.user, [data["from_address"]])
        from_address = authorized_wallets.addresses[0]

        transfer_service = TransferService()
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
                    "contract_address": TransferService.contract_address(token),
                },
                "from_address": from_address,
                "to_address": data["to_address"],
                "amount": data["amount"],
                "transaction_data": tx_data,
            }
        )

    @action(detail=False, methods=["post"])
    def broadcast(self, request):
        serializer = BroadcastTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        transfer_service = TransferService()

        tx_hash, receipt = transfer_service.broadcast_transfer(data["signed_transaction"])

        return Response(
            {
                "tx_hash": tx_hash,
                "block_number": receipt.get("blockNumber"),
                "gas_used": receipt.get("gasUsed"),
            }
        )
