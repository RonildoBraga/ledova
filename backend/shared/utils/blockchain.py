import re
from typing import Optional, Tuple

# keccak256 selectors of the custom errors declared in contracts/contracts/*.sol
# (OpenZeppelin ERC20 + AtomicSwap, ShareToken, AUSG, WhitelistRegistry).
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
}


def decode_revert_reason(error_data: str) -> Tuple[Optional[str], Optional[str], dict]:
    if not error_data or len(error_data) < 10:
        return None, None, {}

    selector = error_data[:10].lower()

    if selector not in ERROR_SELECTORS:
        return None, f"Unknown error (selector: {selector})", {}

    error_name, base_message = ERROR_SELECTORS[selector]
    params = {}

    if len(error_data) >= 74:
        try:
            if error_name == "ERC20InsufficientBalance":
                params["address"] = "0x" + error_data[34:74]
                if len(error_data) >= 138:
                    params["balance"] = int(error_data[74:138], 16)
                if len(error_data) >= 202:
                    params["needed"] = int(error_data[138:202], 16)

            elif error_name == "ERC20InsufficientAllowance":
                params["spender"] = "0x" + error_data[34:74]
                if len(error_data) >= 138:
                    params["allowance"] = int(error_data[74:138], 16)
                if len(error_data) >= 202:
                    params["needed"] = int(error_data[138:202], 16)

        except (ValueError, IndexError):
            pass

    return error_name, base_message, params


def decode_exception_to_message(exception: Exception, default_message: str = "Transaction failed") -> str:
    # web3 surfaces custom-error reverts as the raw selector+args hex in the exception text.
    matches = re.findall(r"0x[a-fA-F0-9]{8,}", str(exception))
    error_data = max(matches, key=len) if matches else None

    if error_data:
        error_name, message, params = decode_revert_reason(error_data)
        if message:
            if error_name == "ERC20InsufficientBalance":
                balance = params.get("balance", 0)
                needed = params.get("needed", 0)
                return f"Insufficient balance: you have {balance:,} tokens but need {needed:,}"
            if error_name == "ERC20InsufficientAllowance":
                allowance = params.get("allowance", 0)
                needed = params.get("needed", 0)
                return f"Insufficient allowance: approved {allowance:,} but need {needed:,}"
            return message

    return default_message
