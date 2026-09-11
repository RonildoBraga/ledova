import re


def _transaction_hash(value):
    if isinstance(value, bytes):
        value = value.hex()
    if not isinstance(value, str):
        return None
    value = value.lower().removeprefix("0x")
    return value if re.fullmatch(r"[0-9a-f]{64}", value) else None


def transaction_hash_matches(observed, expected):
    expected = _transaction_hash(expected)
    return expected is not None and _transaction_hash(observed) == expected
