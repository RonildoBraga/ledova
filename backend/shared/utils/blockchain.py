from typing import Optional, Tuple

ERROR_SELECTORS = {
    "0xe450d38c": ("ERC20InsufficientBalance", "Insufficient token balance"),
    "0xfb8f41b2": ("ERC20InsufficientAllowance", "Insufficient token allowance"),
    "0x94280d62": ("ERC20InvalidReceiver", "Invalid token receiver address"),
    "0xe602df05": ("ERC20InvalidApprover", "Invalid token approver address"),
    "0x96c6fd1e": ("ERC20InvalidSpender", "Invalid token spender address"),
    "0xd92e233d": ("ZeroAddress", "Cannot use zero address"),
    "0x32da96a3": ("TokenNotApproved", "Share token is not approved for trading"),
    "0xa4b885b3": ("PaymentTokenNotApproved", "Payment token is not approved"),
    "0xc64891a5": ("SellerNotWhitelisted", "Seller is not whitelisted"),
    "0xdf8bf18b": ("BuyerNotWhitelisted", "Buyer is not whitelisted"),
    "0xc5487b9a": ("SwapExpired", "Swap order has expired"),
    "0xe9eded21": ("SwapAlreadyUsed", "Swap nonce has already been used"),
    "0x162908e3": ("InvalidSignature", "Invalid signature provided"),
    "0x8bdf9091": ("RecipientNotWhitelisted", "Recipient is not whitelisted for transfers"),
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


def format_balance_error(error_data: str, token_symbol: str = "tokens") -> str:
    error_name, base_message, params = decode_revert_reason(error_data)

    if error_name == "ERC20InsufficientBalance":
        balance = params.get("balance", 0)
        needed = params.get("needed", 0)
        return f"Insufficient balance: you have {balance:,} {token_symbol} but need {needed:,}"

    if error_name == "ERC20InsufficientAllowance":
        allowance = params.get("allowance", 0)
        needed = params.get("needed", 0)
        return f"Insufficient allowance: approved {allowance:,} but need {needed:,} {token_symbol}"

    if base_message:
        return base_message

    return f"Transaction failed: {error_data[:66]}..."


def extract_error_data_from_exception(exception: Exception) -> Optional[str]:
    error_str = str(exception)

    import re

    hex_pattern = r"0x[a-fA-F0-9]{8,}"
    matches = re.findall(hex_pattern, error_str)

    if matches:
        return max(matches, key=len)

    return None


def decode_exception_to_message(exception: Exception, default_message: str = "Transaction failed") -> str:
    error_data = extract_error_data_from_exception(exception)

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
