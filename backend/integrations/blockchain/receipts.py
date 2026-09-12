import re


def normalized_hash(value):
    if isinstance(value, bytes):
        value = value.hex()
    if not isinstance(value, str):
        return None
    value = value.lower().removeprefix("0x")
    return value if re.fullmatch(r"[0-9a-f]{64}", value) else None


def transaction_hash_matches(observed, expected):
    expected = normalized_hash(expected)
    return expected is not None and normalized_hash(observed) == expected


def nonnegative_integer(value, *, maximum, encoded=False):
    if encoded and isinstance(value, str):
        if len(value) <= 78 and re.fullmatch(r"(?:0x[0-9a-fA-F]+|[0-9]+)", value):
            value = int(value, 16 if value.startswith("0x") else 10)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        return None
    return value
