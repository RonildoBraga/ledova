import re
from typing import Optional, Tuple

ERROR_SELECTORS = {
    "0xe450d38c": ("ERC20InsufficientBalance", "Insufficient token balance"),
    "0xfb8f41b2": ("ERC20InsufficientAllowance", "Insufficient token allowance"),
    "0xec442f05": ("ERC20InvalidReceiver", "Invalid token receiver address"),
    "0x96c6fd1e": ("ERC20InvalidSender", "Invalid token sender address"),
    "0x94280d62": ("ERC20InvalidSpender", "Invalid token spender address"),
    "0xe602df05": ("ERC20InvalidApprover", "Invalid token approver address"),
    "0x32da96a3": ("TokenNotApproved", "Share token is not approved for trading"),
    "0xa4b885b3": ("PaymentTokenNotApproved", "Payment token is not approved"),
    "0xdf17e316": ("NotWhitelisted", "Account is not whitelisted"),
    "0xc56873ba": ("OrderExpired", "Swap order has expired"),
    "0xe90aded4": ("NonceAlreadyUsed", "Swap nonce has already been used"),
    "0x42d750dc": ("InvalidSignature", "Invalid signature provided"),
    "0xab0b880c": ("RecipientNotWhitelisted", "Recipient is not whitelisted for transfers"),
    "0xc64891a5": ("NotRelayer", "Caller is not the swap relayer"),
    "0x0309d3fc": ("SameParty", "Buyer and seller must be different accounts"),
    "0x2c5211c6": ("InvalidAmount", "Invalid amount"),
    "0xd93c0665": ("EnforcedPause", "Token transfers are paused"),
}


def decode_revert_reason(error_data: str) -> Tuple[Optional[str], Optional[str], dict]:
    if not isinstance(error_data, str) or len(error_data) > 2050:
        return None, None, {}
    if not re.fullmatch(r"0x(?:[a-fA-F0-9]{2}){4,1024}", error_data):
        return None, None, {}
    selector = error_data[:10].lower()
    if selector not in ERROR_SELECTORS:
        return None, None, {}

    error_name, base_message = ERROR_SELECTORS[selector]
    params = {}
    if len(error_data) == 202 and error_data[10:34] == "0" * 24:
        if error_name == "ERC20InsufficientBalance":
            params = {
                "address": "0x" + error_data[34:74],
                "balance": int(error_data[74:138], 16),
                "needed": int(error_data[138:202], 16),
            }
        elif error_name == "ERC20InsufficientAllowance":
            params = {
                "spender": "0x" + error_data[34:74],
                "allowance": int(error_data[74:138], 16),
                "needed": int(error_data[138:202], 16),
            }
    return error_name, base_message, params


URL_TEXT = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
REVERT_TEXT = re.compile(
    r"(?:execution\s+)?reverted(?:\s+with\s+(?:data|custom\s+error))?\s*[:=]?\s*['\"]?"
    r"(0x[a-fA-F0-9]{8,2048})(?![a-fA-F0-9])",
    re.IGNORECASE,
)


def _revert_payloads(exception):
    pending = [exception]
    seen = set()
    for _ in range(64):
        if not pending:
            break
        value = pending.pop()
        if isinstance(value, (BaseException, dict, list, tuple)):
            if id(value) in seen:
                continue
            seen.add(id(value))
        if isinstance(value, BaseException):
            pending.extend(value.args[:8])
            pending.append(getattr(value, "data", None))
            pending.append(value.__cause__ or (None if value.__suppress_context__ else value.__context__))
        elif isinstance(value, dict):
            pending.extend(
                value.get(key) for key in ("message", "error", "originalError", "data", "returnData", "return")
            )
        elif isinstance(value, (list, tuple)):
            pending.extend(value[:8])
        elif isinstance(value, bytes):
            if 4 <= len(value) <= 1024:
                yield "0x" + value.hex()
        elif isinstance(value, str):
            if len(value) <= 2050 and re.fullmatch(r"0x[0-9a-fA-F]+", value):
                yield value
            else:
                yield from REVERT_TEXT.findall(URL_TEXT.sub("", value[:16384]))[:8]


def decode_exception_to_message(exception: Exception, default_message: str = "Transaction failed") -> str:
    reasons = {}
    details = set()
    for error_data in _revert_payloads(exception):
        error_name, message, params = decode_revert_reason(error_data)
        if not error_name or not message:
            continue
        reasons[error_name] = message
        if error_name == "ERC20InsufficientBalance" and params:
            message = f"Insufficient balance: you have {params['balance']:,} base units but need {params['needed']:,}"
        elif error_name == "ERC20InsufficientAllowance" and params:
            message = (
                f"Insufficient allowance: approved {params['allowance']:,} base units but need {params['needed']:,}"
            )
        if params:
            details.add(message)
    if len(reasons) != 1 or len(details) > 1:
        return default_message
    return details.pop() if details else next(iter(reasons.values()))
