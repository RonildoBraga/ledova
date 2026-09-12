from django.core.exceptions import ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

ACN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 1)
ABN_WEIGHTS = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)
ACN_LENGTH = 9
ABN_LENGTH = 11
ABN_MODULUS = 89

ACN_MALFORMED = "An ACN is exactly 9 digits."
ACN_CHECK_FAILED = "This is not a valid ACN: its last digit does not check out against the other eight."
ACN_ALREADY_REGISTERED = "This ACN is already registered."
ABN_MALFORMED = "An ABN is exactly 11 digits."
ABN_CHECK_FAILED = "This is not a valid ABN: it does not satisfy the ABN check."
ABN_DOES_NOT_CARRY_ACN = (
    "An Australian company's ABN is its ACN with two check digits in front, so its last 9 digits must be the ACN."
)


def digits_of(value) -> str:
    return str(value or "").replace(" ", "").replace("-", "")


def acn_check_digit(acn: str) -> int:
    total = sum(int(digit) * weight for digit, weight in zip(acn, ACN_WEIGHTS))
    return (10 - total % 10) % 10


def acn_is_valid(acn: str) -> bool:
    return len(acn) == ACN_LENGTH and acn.isdigit() and acn_check_digit(acn) == int(acn[-1])


def abn_is_valid(abn: str) -> bool:
    if len(abn) != ABN_LENGTH or not abn.isdigit():
        return False
    weighted = [int(digit) for digit in abn]
    weighted[0] -= 1
    return sum(digit * weight for digit, weight in zip(weighted, ABN_WEIGHTS)) % ABN_MODULUS == 0


def validate_acn(value) -> None:
    acn = digits_of(value)
    if len(acn) != ACN_LENGTH or not acn.isdigit():
        raise ValidationError(ACN_MALFORMED)
    if not acn_is_valid(acn):
        raise ValidationError(ACN_CHECK_FAILED)


def validate_abn(value) -> None:
    abn = digits_of(value)
    if len(abn) != ABN_LENGTH or not abn.isdigit():
        raise ValidationError(ABN_MALFORMED)
    if not abn_is_valid(abn):
        raise ValidationError(ABN_CHECK_FAILED)


def abn_carries_acn(abn: str, acn: str) -> bool:
    return digits_of(abn)[2:] == digits_of(acn)


def checked_acn(value):
    acn = digits_of(value)
    if len(acn) != ACN_LENGTH or not acn.isdigit():
        raise DRFValidationError(ACN_MALFORMED)
    if not acn_is_valid(acn):
        raise DRFValidationError(ACN_CHECK_FAILED)
    return acn


def an_acn_no_other_company_holds(value):
    from companies.models import Company
    from shared.db import use_operator

    acn = checked_acn(value)
    with use_operator():
        if Company.objects.filter(acn=acn).exists():
            raise DRFValidationError(ACN_ALREADY_REGISTERED)
    return acn


def checked_abn(value):
    if not value:
        return value
    abn = digits_of(value)
    if len(abn) != ABN_LENGTH or not abn.isdigit():
        raise DRFValidationError(ABN_MALFORMED)
    if not abn_is_valid(abn):
        raise DRFValidationError(ABN_CHECK_FAILED)
    return abn


def with_matching_identifiers(serializer, data):
    instance = serializer.instance
    acn = data.get("acn", getattr(instance, "acn", ""))
    abn = data.get("abn", getattr(instance, "abn", ""))
    if abn and acn and not abn_carries_acn(abn, acn):
        raise DRFValidationError({"abn": ABN_DOES_NOT_CARRY_ACN})
    return data
