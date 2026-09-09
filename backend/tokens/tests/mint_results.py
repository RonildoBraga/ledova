from tokens.models import ShareIssuance


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
