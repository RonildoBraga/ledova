from collections.abc import Mapping
from decimal import Decimal, InvalidOperation, localcontext

from django.conf import settings

from integrations.blockchain.bitcoin_transactions import (
    MAX_MONEY,
    bitcoin_address_for_script,
    script_for_bitcoin_address,
)
from integrations.blockchain.receipts import normalized_hash, transaction_hash_matches
from wallets.exceptions import InvalidTransactionException

GENESIS_HASHES = {
    "test": "000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943",
    "regtest": "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206",
}


def verified_bitcoin_network(client, expected=None):
    expected = expected or settings.BITCOIN_NETWORK
    if (
        expected not in GENESIS_HASHES
        or expected != settings.BITCOIN_NETWORK
        or client.assert_expected_network() != expected
        or not transaction_hash_matches(client.get_genesis_hash(), GENESIS_HASHES[expected])
    ):
        raise InvalidTransactionException("The Bitcoin endpoint does not match the recorded test network.")
    return expected


def satoshis(value):
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        raise InvalidTransactionException("The Bitcoin previous-output value is invalid.")
    try:
        amount = Decimal(value)
        if not amount.is_finite() or len(amount.as_tuple().digits) > 40 or abs(amount.as_tuple().exponent) > 40:
            raise ValueError
        with localcontext() as context:
            context.prec = 50
            amount *= 100_000_000
            if amount != amount.to_integral_value() or not 0 <= amount <= MAX_MONEY:
                raise ValueError
            return int(amount)
    except (InvalidOperation, ValueError):
        raise InvalidTransactionException("The Bitcoin previous-output value is invalid.") from None


def bitcoin_transfer_outputs(decoded, sender_address, network):
    try:
        sender_script = script_for_bitcoin_address(sender_address, network)
        recipients = {}
        for output in decoded.outputs:
            if output.script != sender_script:
                address = bitcoin_address_for_script(output.script, network)
                recipients[address] = recipients.get(address, 0) + output.satoshis
    except ValueError:
        raise InvalidTransactionException(
            "The Bitcoin transfer contains an unsupported test address or script."
        ) from None
    if len(recipients) != 1 or next(iter(recipients.values())) <= 0:
        raise InvalidTransactionException(
            "A Bitcoin transfer requires one external recipient plus optional wallet change."
        )
    recipient, amount = next(iter(recipients.items()))
    return sender_script, recipient, amount


def observe_bitcoin_inputs(client, decoded, sender_script):
    inputs = []
    for item in decoded.inputs:
        previous = client.get_previous_output(item.tx_hash, item.output_index)
        if not isinstance(previous, Mapping):
            raise InvalidTransactionException("A Bitcoin previous output is unavailable; its ownership is unresolved.")
        details = previous.get("scriptPubKey")
        if not isinstance(details, Mapping) or details.get("hex") != sender_script.hex():
            raise InvalidTransactionException("Every Bitcoin input must belong to this wallet.")
        block_hash = normalized_hash(previous.get("bestblock"))
        if block_hash is None:
            raise InvalidTransactionException("The Bitcoin input observation has no valid block identity.")
        inputs.append(
            {
                "tx_hash": item.tx_hash,
                "output_index": item.output_index,
                "satoshis": satoshis(previous.get("value")),
                "script": sender_script.hex(),
                "observed_block_hash": block_hash,
            }
        )
    if sum(item["satoshis"] for item in inputs) > MAX_MONEY:
        raise InvalidTransactionException("Bitcoin input values exceed the supported supply.")
    return inputs


def check_bitcoin_admission(client, decoded, fee, *, allow_known=False):
    observations = client.check_mempool_acceptance(decoded.raw.hex())
    if not isinstance(observations, list) or len(observations) != 1 or not isinstance(observations[0], Mapping):
        raise InvalidTransactionException("The Bitcoin signed transaction could not be verified.")
    observation = observations[0]
    if not transaction_hash_matches(observation.get("txid"), decoded.tx_hash) or not transaction_hash_matches(
        observation.get("wtxid"), decoded.witness_hash
    ):
        raise InvalidTransactionException("The Bitcoin verification response has a different signed identity.")
    if observation.get("allowed") is True:
        fees = observation.get("fees")
        if not isinstance(fees, Mapping) or satoshis(fees.get("base")) != fee:
            raise InvalidTransactionException("The Bitcoin verified fee does not match the signed inputs and outputs.")
        return "allowed"
    if allow_known:
        known = client.get_transaction(decoded.tx_hash)
        mempool = client.get_mempool_entry(decoded.tx_hash)
        if (
            isinstance(known, Mapping)
            and isinstance(mempool, Mapping)
            and transaction_hash_matches(mempool.get("wtxid"), decoded.witness_hash)
            and known.get("hex") == decoded.raw.hex()
            and transaction_hash_matches(known.get("txid"), decoded.tx_hash)
            and transaction_hash_matches(known.get("hash"), decoded.witness_hash)
        ):
            return "known"
    raise InvalidTransactionException("The Bitcoin signed transaction was not accepted by node validation.")


def prepare_bitcoin_intent(client, decoded, wallet):
    network = verified_bitcoin_network(client)
    sender_script, recipient, amount = bitcoin_transfer_outputs(decoded, wallet.address, network)
    inputs = observe_bitcoin_inputs(client, decoded, sender_script)
    fee = sum(item["satoshis"] for item in inputs) - sum(output.satoshis for output in decoded.outputs)
    if fee < 0:
        raise InvalidTransactionException("Bitcoin outputs exceed the recorded input values.")
    check_bitcoin_admission(client, decoded, fee)
    verified_bitcoin_network(client, network)
    return {
        "network": network,
        "genesis_hash": GENESIS_HASHES[network],
        "sender_address": wallet.address,
        "to_address": recipient,
        "amount_satoshis": amount,
        "fee_satoshis": fee,
        "version": decoded.version,
        "lock_time": decoded.lock_time,
        "inputs": inputs,
        "outputs": [{"satoshis": output.satoshis, "script": output.script.hex()} for output in decoded.outputs],
    }
