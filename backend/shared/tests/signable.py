JAVASCRIPT_SAFE_INTEGER = 2**53 - 1


def unsafe_numbers(payload):
    if isinstance(payload, bool):
        return []
    if isinstance(payload, (int, float)):
        return [payload] if abs(payload) > JAVASCRIPT_SAFE_INTEGER else []
    if isinstance(payload, dict):
        return [found for value in payload.values() for found in unsafe_numbers(value)]
    if isinstance(payload, (list, tuple)):
        return [found for value in payload for found in unsafe_numbers(value)]
    return []


def assert_signable(case, payload):
    case.assertEqual(
        unsafe_numbers(payload),
        [],
        "a signable payload may not carry a number JSON.parse would round",
    )
