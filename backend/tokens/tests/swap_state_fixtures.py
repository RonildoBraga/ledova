import secrets
from unittest.mock import Mock

from django.conf import settings
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from shared.tests.settlement import save_swap_with_context
from shared.tests.tenants import make_tenant
from tokens.models import (
    SwapOrder,
    SwapOrderStatus,
    TransferOrder,
    TransferOrderStatus,
    TransferOrderType,
)
from tokens.services import AtomicSwapService
from tokens.services.settlement_context import (
    recorded_settlement_context,
    settlement_execution_arguments,
)
from wallets.models import Wallet

CONTRACT = "0x" + "9d" * 20
TX_HASH = "0x" + "ab" * 32
OTHER_HASH = "0x" + "cd" * 32
SELLER = Account.from_key("0x" + "31" * 32)
BUYER = Account.from_key("0x" + "32" * 32)
CONFIRMED = {"status": 1, "blockNumber": 7, "blockHash": "0x" + "ef" * 32, "gasUsed": 21000}
REVERTED = {"status": 0, "blockNumber": 8, "blockHash": "0x" + "fa" * 32, "gasUsed": 21000}


def swap_service():
    service = object.__new__(AtomicSwapService)
    service.chain_client = Mock(chain_id=settings.BLOCKCHAIN_CHAIN_ID)
    service.chain_client.assert_expected_chain = Mock(return_value=settings.BLOCKCHAIN_CHAIN_ID)
    service.chain_client.w3.eth.chain_id = settings.BLOCKCHAIN_CHAIN_ID
    service.chain_client.to_checksum_address.side_effect = Web3.to_checksum_address
    service.whitelist_service = Mock()
    return service


def make_swap(label, *, ready=False):
    tenant = make_tenant(label)
    orders = []
    for key, order_type in ((SELLER, TransferOrderType.SELL), (BUYER, TransferOrderType.BUY)):
        wallet = Wallet.objects.create(user_account=tenant.account, address=key.address, chain="base")
        orders.append(
            TransferOrder.objects.create(
                token=tenant.deployed_token,
                payment_asset=tenant.refs.stablecoin,
                wallet=wallet,
                owner_account=tenant.account,
                wallet_address=wallet.address,
                order_type=order_type,
                quantity=40,
                filled_quantity=30,
                price_per_share="1.50",
                status=TransferOrderStatus.PENDING_SIGNATURE,
            )
        )
    swap = SwapOrder(
        sell_order=orders[0],
        buy_order=orders[1],
        share_token=tenant.deployed_token,
        payment_asset=tenant.refs.stablecoin,
        seller_address=SELLER.address,
        buyer_address=BUYER.address,
        share_amount=10,
        payment_amount=1500,
        nonce=secrets.randbits(63),
        order_hash="0x" + secrets.token_hex(32),
    )
    save_swap_with_context(swap)
    service = swap_service()
    if ready:
        signable = encode_typed_data(full_message=service.get_typed_data(swap))
        swap.seller_signature = SELLER.sign_message(signable).signature.hex()
        swap.buyer_signature = BUYER.sign_message(signable).signature.hex()
        swap.status = SwapOrderStatus.READY
    swap.save()
    return swap


def transaction_for(swap, tx_hash=TX_HASH, status=TransactionStatus.SUBMITTED):
    return BlockchainTransaction.objects.create(
        tx_type=TransactionType.ATOMIC_SWAP,
        status=status,
        tx_hash=tx_hash,
        from_address=SELLER.address,
        to_address=recorded_settlement_context(swap)["typed_data"]["domain"]["verifyingContract"],
        function_name="executeSwap",
        function_args=settlement_execution_arguments(swap),
        related_model="tokens.SwapOrder",
        related_uuid=swap.pk,
    )


def attach_claim(swap, tx_hash=TX_HASH, status=TransactionStatus.SUBMITTED):
    transaction = transaction_for(swap, tx_hash, status)
    swap.transaction = transaction
    swap.tx_hash = tx_hash or ""
    swap.status = SwapOrderStatus.EXECUTING
    swap.save(update_fields=["transaction", "tx_hash", "status"])
    return transaction


def persisted_outcome(swap):
    return (
        SwapOrder.objects.filter(pk=swap.pk).values().get(),
        list(BlockchainTransaction.objects.filter(related_uuid=swap.pk).order_by("pk").values()),
        list(TransferOrder.objects.filter(pk__in=[swap.sell_order_id, swap.buy_order_id]).order_by("pk").values()),
    )
