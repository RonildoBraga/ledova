from decimal import Decimal, localcontext


def token_base_units(amount: Decimal, decimals: int) -> int:
    if not amount.is_finite() or amount <= 0 or not 0 <= decimals <= 255:
        raise ValueError("Invalid token amount")
    _, digits, exponent = amount.as_tuple()
    discarded_places = max(0, -exponent - decimals)
    if discarded_places and any(digits[-discarded_places:]):
        raise ValueError("Token amount exceeds deployment precision")
    if amount.adjusted() + decimals >= 78:
        raise ValueError("Token amount exceeds uint256")
    with localcontext() as context:
        context.prec = max(78, len(digits))
        scaled = amount.scaleb(decimals)
    units = int(scaled)
    if units >= 2**256:
        raise ValueError("Token amount exceeds uint256")
    return units
