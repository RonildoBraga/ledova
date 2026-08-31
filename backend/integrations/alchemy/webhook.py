import hashlib
import hmac
import logging
from typing import Optional

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from wallets.models import Transaction, Wallet
from wallets.tasks import confirm_pending_transaction

logger = logging.getLogger("ledova_backend")


def verify_alchemy_signature(payload: bytes, signature: str, signing_key: str) -> bool:
    if not signing_key or not signature:
        return False

    expected = hmac.new(
        signing_key.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


@method_decorator(csrf_exempt, name="dispatch")
class AlchemyWebhookView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        signature = request.headers.get("X-Alchemy-Signature", "")
        signing_key = getattr(settings, "ALCHEMY_WEBHOOK_SIGNING_KEY", "")

        if signing_key and not verify_alchemy_signature(request.body, signature, signing_key):
            logger.warning("[WEBHOOK:ALCHEMY] Invalid signature")
            return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            data = request.data
            webhook_type = data.get("type")
            event = data.get("event", {})

            logger.info(f"[WEBHOOK:ALCHEMY] Received webhook: {webhook_type}")

            if webhook_type == "ADDRESS_ACTIVITY":
                self._handle_address_activity(event)
            elif webhook_type == "MINED_TRANSACTION":
                self._handle_mined_transaction(event)
            else:
                logger.info(f"[WEBHOOK:ALCHEMY] Unhandled webhook type: {webhook_type}")

            return Response({"success": True}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"[WEBHOOK:ALCHEMY] Error processing webhook: {e}", exc_info=True)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _handle_address_activity(self, event: dict) -> None:
        activity = event.get("activity", [])

        for item in activity:
            tx_hash = item.get("hash")
            if not tx_hash:
                continue

            from_address = item.get("fromAddress", "").lower()
            to_address = item.get("toAddress", "").lower()

            wallet = self._find_wallet_by_address(from_address, to_address)
            if not wallet:
                continue

            block_num = item.get("blockNum")
            if isinstance(block_num, str) and block_num.startswith("0x"):
                block_num = int(block_num, 16)

            self._process_transaction_confirmation(
                tx_hash=tx_hash,
                wallet=wallet,
                block_number=block_num,
            )

    def _handle_mined_transaction(self, event: dict) -> None:
        transaction = event.get("transaction", {})
        tx_hash = transaction.get("hash")

        if not tx_hash:
            return

        from_address = transaction.get("from", "").lower()
        to_address = transaction.get("to", "").lower()

        wallet = self._find_wallet_by_address(from_address, to_address)
        if not wallet:
            return

        block_number = transaction.get("blockNumber")
        if isinstance(block_number, str) and block_number.startswith("0x"):
            block_number = int(block_number, 16)

        self._process_transaction_confirmation(
            tx_hash=tx_hash,
            wallet=wallet,
            block_number=block_number,
        )

    def _find_wallet_by_address(self, from_address: str, to_address: str) -> Optional[Wallet]:
        wallet = Wallet.objects.filter(address__iexact=from_address).first()
        if wallet:
            return wallet
        return Wallet.objects.filter(address__iexact=to_address).first()

    def _process_transaction_confirmation(
        self,
        tx_hash: str,
        wallet: Wallet,
        block_number: Optional[int] = None,
    ) -> None:
        try:
            tx = Transaction.objects.filter(tx_hash=tx_hash, wallet=wallet).first()

            if tx and tx.status == "pending":
                confirm_pending_transaction.defer(tx_hash=tx_hash, wallet_uuid=str(wallet.uuid))
                logger.info(f"[WEBHOOK:ALCHEMY] Queued confirmation for pending tx: {tx_hash}")
            elif not tx:
                from wallets.tasks import sync_wallet

                sync_wallet.defer(wallet_uuid=str(wallet.uuid))
                logger.info(f"[WEBHOOK:ALCHEMY] Queued wallet sync for new tx: {tx_hash}")
            else:
                logger.debug(f"[WEBHOOK:ALCHEMY] Transaction already processed: {tx_hash}")

        except Exception as e:
            logger.error(f"[WEBHOOK:ALCHEMY] Error processing tx {tx_hash}: {e}")
