import hashlib
import hmac
import logging

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.webhooks import is_stale
from shared.constants import BLOCKCHAIN_BASE, BLOCKCHAIN_ETHEREUM
from shared.db.middleware import RunsOnTheOperatorConnection
from wallets.models import Transaction, Wallet
from wallets.tasks import confirm_pending_transaction

logger = logging.getLogger(__name__)

NETWORKS = {
    "BASE_SEPOLIA": (BLOCKCHAIN_BASE, 84532, "BLOCKCHAIN_CHAIN_ID"),
    "ETH_SEPOLIA": (BLOCKCHAIN_ETHEREUM, 11155111, "ETHEREUM_CHAIN_ID"),
}


def event_chain(event):
    network = event.get("network") if isinstance(event, dict) else None
    definition = NETWORKS.get(network) if isinstance(network, str) else None
    if definition is None:
        return None
    chain, chain_id, setting = definition
    return chain if getattr(settings, setting) == chain_id else None


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
class AlchemyWebhookView(RunsOnTheOperatorConnection, APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(exclude=True)
    def post(self, request):
        signature = request.headers.get("X-Alchemy-Signature", "")
        signing_key = getattr(settings, "ALCHEMY_WEBHOOK_SIGNING_KEY", "")

        if not signing_key or not verify_alchemy_signature(request.body, signature, signing_key):
            logger.warning(
                "Rejected webhook: %s",
                "signing key not configured" if not signing_key else "invalid signature",
            )
            return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            data = request.data
            webhook_type = data.get("type")
            event = data.get("event", {})

            if is_stale(data):
                logger.warning("Rejected webhook: timestamp outside the freshness window")
                return Response({"error": "Stale webhook"}, status=status.HTTP_400_BAD_REQUEST)

            chain = event_chain(event)
            if webhook_type in {"ADDRESS_ACTIVITY", "MINED_TRANSACTION"} and chain is None:
                return Response(
                    {"error": "Unsupported or mismatched webhook network"}, status=status.HTTP_400_BAD_REQUEST
                )

            if webhook_type == "ADDRESS_ACTIVITY":
                self._handle_address_activity(event, chain)
            elif webhook_type == "MINED_TRANSACTION":
                self._handle_mined_transaction(event, chain)
            else:
                logger.warning("Unhandled webhook type: %s", webhook_type)

            return Response({"success": True}, status=status.HTTP_200_OK)

        except Exception:
            logger.exception("Error processing webhook")
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _handle_address_activity(self, event: dict, chain: str) -> None:
        activity = event.get("activity", [])
        seen = set()

        for item in activity:
            tx_hash = item.get("hash")
            if not tx_hash:
                continue

            from_address = (item.get("fromAddress") or "").lower()
            to_address = (item.get("toAddress") or "").lower()

            for wallet in self._wallets_by_address(from_address, to_address, chain):
                key = (tx_hash, wallet.pk)
                if key not in seen:
                    seen.add(key)
                    self._process_transaction_confirmation(tx_hash=tx_hash, wallet=wallet)

    def _handle_mined_transaction(self, event: dict, chain: str) -> None:
        transaction = event.get("transaction", {})
        tx_hash = transaction.get("hash")

        if not tx_hash:
            return

        from_address = (transaction.get("from") or "").lower()
        to_address = (transaction.get("to") or "").lower()

        for wallet in self._wallets_by_address(from_address, to_address, chain):
            self._process_transaction_confirmation(tx_hash=tx_hash, wallet=wallet)

    def _wallets_by_address(self, from_address: str, to_address: str, chain: str):
        wallets = Wallet.objects.none()
        for address in {from_address, to_address} - {""}:
            wallets |= Wallet.objects.filter_by_address(address, chain=chain)
        return wallets.order_by("uuid")

    def _process_transaction_confirmation(self, tx_hash: str, wallet: Wallet) -> None:
        try:
            tx = Transaction.objects.filter(tx_hash=tx_hash, wallet=wallet, chain=wallet.chain).first()

            if tx and tx.status == "pending":
                confirm_pending_transaction.defer(tx_hash=tx_hash, wallet_uuid=str(wallet.uuid), principal_id=None)
            elif not tx:
                from wallets.tasks import sync_wallet

                sync_wallet.defer(wallet_uuid=str(wallet.uuid))

        except Exception:
            logger.exception("Error processing a webhook transaction")
