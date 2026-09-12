from integrations.blockchain.receipts import transaction_hash_matches


def apply_receipt_metadata(tx, *, block_hash=None, block_number=None, block_timestamp=None, actual_fee=None):
    changed_block = (block_hash is not None and not transaction_hash_matches(block_hash, tx.block_hash)) or (
        block_number is not None and block_number != tx.block_number
    )
    values = {
        "block_hash": block_hash,
        "block_number": block_number,
        "block_timestamp": block_timestamp,
        "transaction_fee": actual_fee,
    }
    fields = []
    for field, value in values.items():
        if value is not None or changed_block:
            setattr(tx, field, value)
            fields.append(field)
    return fields
