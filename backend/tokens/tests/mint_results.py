from web3 import Web3

from tokens.models import ShareIssuance

MINT_HASH = Web3.to_hex(Web3.keccak(b"synthetic-mint"))


def signed_mint_transaction(*args, on_signed, **kwargs):
    on_signed(MINT_HASH, b"synthetic-mint")
    return MINT_HASH, None


def recorded_mint_result(result):
    def mint(contract_address, recipient, amount, **kwargs):
        issuance = ShareIssuance.objects.get(
            token__contract_address=contract_address,
            recipient_address=recipient,
            amount=str(amount),
            status="processing",
        )
        issuance.mark_processing(tx_hash=result["tx_hash"])
        return result

    return mint
