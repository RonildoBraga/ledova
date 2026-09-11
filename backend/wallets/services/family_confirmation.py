import hashlib
import json
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from django.core.serializers.json import DjangoJSONEncoder

from shared.db import atomic, use_operator
from wallets.exceptions import InvalidTransactionException
from wallets.models import (
    Transaction,
    Wallet,
    WalletChainObservation,
    WalletChainWatch,
    WalletSubmission,
    WalletSubmissionFamily,
)
from wallets.services.family_balances import (
    capture_balance_target,
    install_projection,
    read_balance_state,
)
from wallets.services.receipt_metadata import apply_receipt_metadata
from wallets.services.receipt_targets import capture_receipt_target


def _fingerprint(wallet, tx):
    return hashlib.sha256(
        json.dumps(capture_receipt_target(wallet, tx), cls=DjangoJSONEncoder, separators=(",", ":")).encode()
    ).hexdigest()


def _current_observation(watch, observation):
    return (watch.latest_observation_id, watch.generation, watch.target_fingerprint) == (
        observation.pk,
        observation.generation,
        observation.target_fingerprint,
    )


def _attributed(family, attempt, observation):
    evidence = observation.evidence
    if (
        observation.family_generation != family.generation
        or evidence.get("complete") is not True
        or evidence.get("tx_hash") != attempt.tx_hash
    ):
        return False
    if observation.result == "included":
        receipt = evidence.get("receipt") or {}
        if receipt.get("succeeded") not in (True, False) or evidence.get("canonical_receipt") != {
            "hash": receipt.get("hash"),
            "height": receipt.get("height"),
        }:
            return False
        if family.winner_id not in (None, attempt.pk):
            return False
        if family.winner_id is not None:
            previous = family.winner_observation.evidence["receipt"]
            if (previous["hash"], previous["height"]) != (receipt["hash"], receipt["height"]):
                return False
        return True
    if (
        observation.result == "orphaned"
        and family.winner_id == attempt.pk
        and evidence.get("previous_orphaned") is True
    ):
        previous = family.winner_observation.evidence["receipt"]
        return evidence.get("previous_block") == {"hash": previous["hash"], "height": previous["height"]}
    return False


def reconcile_family_observation(observation_id, *, client=None):
    with use_operator(), atomic(durable=True):
        observation = WalletChainObservation.objects.select_related("watch").get(pk=observation_id)
        wallet = Wallet.objects.select_for_update().get(pk=observation.watch.wallet_id)
        watch = WalletChainWatch.objects.select_for_update().get(pk=observation.watch_id)
        attempt = (
            WalletSubmission.objects.select_related("transaction")
            .filter(transaction_id=observation.watch.transaction_id)
            .first()
        )
        if attempt is None:
            return "not_a_family"
        family = WalletSubmissionFamily.objects.select_for_update().get(pk=attempt.family_id)
        if (
            not _current_observation(watch, observation)
            or _fingerprint(wallet, attempt.transaction) != observation.target_fingerprint
            or not _attributed(family, attempt, observation)
        ):
            return "observation_changed"
        try:
            target = capture_balance_target(wallet)
        except InvalidTransactionException:
            target = None
        family_generation = family.generation
    state = None
    if target is not None:
        try:
            state = read_balance_state(wallet, target["assets"], client=client)
            if {"hash": state["block_hash"], "height": state["block_number"]} != observation.evidence.get("head") or (
                observation.result == "included" and state["nonce"] <= family.nonce
            ):
                state = None
        except InvalidTransactionException:
            state = None
    with use_operator(), atomic(durable=True):
        wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
        family = WalletSubmissionFamily.objects.select_for_update().get(pk=family.pk)
        watch = WalletChainWatch.objects.select_for_update().get(pk=observation.watch_id)
        attempt = WalletSubmission.objects.select_related("transaction").get(pk=attempt.pk)
        if (
            not _current_observation(watch, observation)
            or family.generation != family_generation
            or _fingerprint(wallet, attempt.transaction) != observation.target_fingerprint
            or not _attributed(family, attempt, observation)
        ):
            return "observation_changed"
        if target is not None:
            try:
                if capture_balance_target(wallet) != target:
                    return "observation_changed"
            except InvalidTransactionException:
                state = None
        if observation.result == "included":
            changed = family.winner_id is None
            if changed:
                family.winner = attempt
                family.winner_observation = observation
                family.generation += 1
                family.save(update_fields=["winner", "winner_observation", "generation", "updated_at"])
            _record_inclusion(family, attempt, observation, changed)
        else:
            family.winner = None
            family.winner_observation = observation
            family.generation += 1
            family.save(update_fields=["winner", "winner_observation", "generation", "updated_at"])
            Transaction.objects.filter(submission__family=family).update(
                status="pending",
                replaced_by_tx_hash=None,
                block_number=None,
                block_hash=None,
                block_timestamp=None,
                transaction_fee=None,
                balance_reconciliation_token=uuid4(),
            )
        if state is not None:
            install_projection(wallet, target, state)
            Transaction.objects.filter(submission__family=family).update(balance_reconciliation_token=None)
            return "reconciled"
        return "reconciliation_pending"


def _record_inclusion(family, attempt, observation, changed):
    from wallets.services.transaction_confirmation import _notify_wallet_users

    receipt = observation.evidence["receipt"]
    tx = Transaction.objects.select_for_update().get(pk=attempt.transaction_id)
    fields = apply_receipt_metadata(
        tx,
        block_hash=receipt["hash"],
        block_number=receipt["height"],
        block_timestamp=datetime.fromisoformat(receipt["timestamp"]) if receipt.get("timestamp") else None,
        actual_fee=Decimal(receipt["actual_fee"]) if receipt.get("actual_fee") is not None else None,
    )
    tx.status = "confirmed" if receipt["succeeded"] else "failed"
    tx.replaced_by_tx_hash = None
    tx.balance_reconciliation_token = tx.balance_reconciliation_token or uuid4()
    tx.save(update_fields=["status", "replaced_by_tx_hash", "balance_reconciliation_token", *fields])
    Transaction.objects.filter(submission__family=family).exclude(pk=tx.pk).update(
        status="replaced", replaced_by_tx_hash=attempt.tx_hash, balance_reconciliation_token=uuid4()
    )
    if changed:
        _notify_wallet_users(tx, tx.status)
