import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import NamedTuple
from uuid import UUID

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from integrations.blockchain import get_blockchain_client
from integrations.blockchain.receipts import nonnegative_integer
from shared.constants import BLOCKCHAIN_BITCOIN, normalize_chain
from shared.db import atomic, use_operator
from wallets.models import (
    BitcoinSubmission,
    Transaction,
    Wallet,
    WalletChainObservation,
    WalletChainWatch,
    WalletSubmission,
)
from wallets.services.chain_evidence import collect_chain_evidence
from wallets.services.nonce_evidence import collect_nonce_evidence
from wallets.services.receipt_readers import MAX_BLOCK_NUMBER
from wallets.services.receipt_targets import ReceiptTarget, capture_receipt_target


class ChainObservationClaim(NamedTuple):
    watch_id: UUID
    transaction_id: UUID
    wallet_id: UUID
    generation: int
    target_fingerprint: str
    target: ReceiptTarget
    chain: str
    network: str
    tx_hash: str
    started_at: datetime
    previous_block: dict | None
    policy: dict
    signed_transaction: bytes | None
    nonce_admission: dict | None


def finality_policy(network, chain):
    configured = getattr(settings, "WALLET_CHAIN_FINALITY_POLICIES", {})
    policy = configured.get(network, {"mode": "unconfigured"}) if isinstance(configured, Mapping) else None
    if not isinstance(policy, Mapping):
        return {"version": 1, "mode": "invalid"}
    mode = policy.get("mode")
    if mode == "depth":
        depth = nonnegative_integer(policy.get("depth"), maximum=MAX_BLOCK_NUMBER)
        if depth is not None and depth > 0:
            return {"version": 1, "mode": mode, "depth": depth}
    elif mode == "unconfigured" or (mode == "finalized" and chain != BLOCKCHAIN_BITCOIN):
        return {"version": 1, "mode": mode}
    return {"version": 1, "mode": "invalid"}


def _journal_identity(wallet, tx):
    evm = WalletSubmission.objects.filter(transaction=tx).first()
    bitcoin = BitcoinSubmission.objects.filter(transaction=tx).first()
    if (evm is None) == (bitcoin is None):
        return None
    journal = evm if evm is not None else bitcoin
    chain = evm.chain if evm is not None else BLOCKCHAIN_BITCOIN
    if (
        journal.wallet_id != wallet.pk
        or journal.user_account_id != wallet.user_account_id
        or tx.user_account_id != wallet.user_account_id
        or journal.tx_hash != tx.tx_hash
        or chain != normalize_chain(wallet.chain)
        or chain != tx.chain
        or tx.imported_from_history
    ):
        return None
    network = f"evm:{evm.chain_id}" if evm is not None else "bitcoin:" + bitcoin.genesis_hash
    return chain, network, journal.tx_hash, evm


def claim_chain_observation(transaction_id):
    with use_operator(), atomic(durable=True):
        wallet_id = Transaction.objects.filter(pk=transaction_id).values_list("wallet_id", flat=True).first()
        if wallet_id is None:
            return None
        wallet = Wallet.objects.select_for_update().get(pk=wallet_id)
        tx = Transaction.objects.select_for_update().get(pk=transaction_id, wallet=wallet)
        identity = _journal_identity(wallet, tx)
        if identity is None:
            return None
        chain, network, tx_hash, evm = identity
        watch, _ = WalletChainWatch.objects.select_for_update().get_or_create(
            transaction=tx,
            defaults={
                "wallet": wallet,
                "user_account_id": wallet.user_account_id,
                "chain": chain,
                "network": network,
                "tx_hash": tx_hash,
            },
        )
        if (watch.wallet_id, watch.user_account_id, watch.chain, watch.network, watch.tx_hash) != (
            wallet.pk,
            wallet.user_account_id,
            chain,
            network,
            tx_hash,
        ):
            return None
        target = capture_receipt_target(wallet, tx)
        fingerprint = hashlib.sha256(
            json.dumps(target, cls=DjangoJSONEncoder, separators=(",", ":")).encode()
        ).hexdigest()
        previous = watch.observations.filter(result="included").first()
        previous_block = previous.evidence.get("receipt") if previous is not None else None
        watch.generation += 1
        watch.target_fingerprint = fingerprint
        watch.last_started_at = timezone.now()
        watch.save(update_fields=["generation", "target_fingerprint", "last_started_at", "updated_at"])
        return ChainObservationClaim(
            watch.pk,
            tx.pk,
            wallet.pk,
            watch.generation,
            fingerprint,
            target,
            chain,
            network,
            tx_hash,
            watch.last_started_at,
            previous_block,
            finality_policy(network, chain),
            bytes(evm.raw_transaction) if evm is not None else None,
            evm.intent.get("mined_nonce_observation") if evm is not None else None,
        )


def complete_chain_observation(claim, result):
    with use_operator(), atomic(durable=True):
        wallet = Wallet.objects.select_for_update().get(pk=claim.wallet_id)
        tx = Transaction.objects.select_for_update().get(pk=claim.transaction_id, wallet=wallet)
        watch = WalletChainWatch.objects.select_for_update().get(pk=claim.watch_id)
        if (
            capture_receipt_target(wallet, tx) != claim.target
            or watch.generation != claim.generation
            or watch.target_fingerprint != claim.target_fingerprint
            or watch.last_started_at != claim.started_at
        ):
            return "observation_changed"
        if watch.observations.filter(generation=claim.generation).exists():
            return "already_recorded"
        observation = WalletChainObservation.objects.create(
            watch=watch,
            user_account_id=watch.user_account_id,
            generation=claim.generation,
            target_fingerprint=claim.target_fingerprint,
            started_at=claim.started_at,
            result=result["result"],
            finality=result["finality"],
            reason=result["reason"],
            policy=claim.policy,
            evidence=result["evidence"],
        )
        watch.latest_observation = observation
        watch.last_completed_at = timezone.now()
        watch.save(update_fields=["latest_observation", "last_completed_at", "updated_at"])
        return "recorded"


def observe_wallet_chain(transaction_id):
    claim = claim_chain_observation(transaction_id)
    if claim is None:
        return "identity_unavailable"
    try:
        client = get_blockchain_client(claim.chain)
        result = collect_chain_evidence(
            client,
            chain=claim.chain,
            network=claim.network,
            tx_hash=claim.tx_hash,
            previous_block=claim.previous_block,
            policy=claim.policy,
        )
        if (
            claim.signed_transaction is not None
            and result["evidence"].get("complete") is True
            and result["reason"] in ("receipt_unavailable", "previous_block_replaced", "receipt_block_replaced")
        ):
            nonce = collect_nonce_evidence(client, claim.signed_transaction, admission=claim.nonce_admission)
            if nonce["result"] in ("candidate", "unconsumed") and (
                nonce["evidence"].get("head") != result["evidence"].get("head")
            ):
                nonce = {
                    "result": "unknown",
                    "reason": "observation_head_changed",
                    "evidence": {**nonce["evidence"], "complete": False},
                }
            result["evidence"]["nonce_spend"] = nonce
    except Exception:
        result = {"result": "unknown", "finality": "unknown", "reason": "provider_unavailable", "evidence": {}}
    return complete_chain_observation(claim, result)
