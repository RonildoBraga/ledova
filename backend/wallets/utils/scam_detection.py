"""
Scam token detection utilities.

This module provides utilities to detect potential scam/fake tokens that attempt
to impersonate legitimate tokens through various deceptive techniques.
"""

import re
from dataclasses import dataclass
from typing import Optional

# Regex to detect non-ASCII characters in token symbols (common scam tactic)
# Scammers use lookalike Unicode characters to impersonate legitimate tokens
# e.g., "EꓔH" (with Unicode ꓔ) instead of "ETH"
VALID_TOKEN_SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9\-_\.]+$")

# Known legitimate token symbols that scammers commonly impersonate
# Maps canonical symbol to list of known lookalike scam variations
KNOWN_TOKENS = {
    "ETH",
    "BTC",
    "USDT",
    "USDC",
    "DAI",
    "WETH",
    "WBTC",
    "LINK",
    "UNI",
    "AAVE",
    "MATIC",  # Legacy Polygon token (migrated to POL)
    "POL",  # New Polygon token
    "SOL",
    "BNB",
    "XRP",
    "ADA",
    "DOGE",
    "SHIB",
    "LTC",
    "AVAX",
    "DOT",
}

# Character substitutions commonly used in scam tokens
# Maps legitimate character to list of lookalike characters
LOOKALIKE_CHARS = {
    "A": ["4", "Α", "А", "Ꭺ"],  # Greek Alpha, Cyrillic A, Cherokee A
    "B": ["8", "Β", "В", "Ᏼ"],  # Greek Beta, Cyrillic Ve, Cherokee
    "C": ["Ϲ", "С", "Ꮯ"],  # Greek Lunate Sigma, Cyrillic Es, Cherokee
    "D": ["Ꭰ"],  # Cherokee Da
    "E": ["3", "Ε", "Е", "Ꭼ"],  # Greek Epsilon, Cyrillic Ie, Cherokee
    "G": ["6", "Ԍ"],  # Cyrillic Ghe with descender
    "H": ["Η", "Н", "Ꮋ"],  # Greek Eta, Cyrillic En, Cherokee
    "I": ["1", "l", "Ι", "І", "Ꮖ", "|"],  # Greek Iota, Cyrillic I, Cherokee, pipe
    "J": ["Ј", "Ꭻ"],  # Cyrillic Je, Cherokee
    "K": ["Κ", "К", "Ꮶ"],  # Greek Kappa, Cyrillic Ka, Cherokee
    "L": ["1", "Ꮮ", "ꓡ"],  # Cherokee, Lisu
    "M": ["Μ", "М", "Ꮇ"],  # Greek Mu, Cyrillic Em, Cherokee
    "N": ["Ν", "Ꮑ"],  # Greek Nu, Cherokee
    "O": ["0", "Ο", "О", "Ꮎ"],  # Greek Omicron, Cyrillic O, Cherokee
    "P": ["Ρ", "Р", "Ꮲ"],  # Greek Rho, Cyrillic Er, Cherokee
    "Q": ["Ԛ"],  # Cyrillic Qa
    "R": ["Ꭱ", "Ꮢ"],  # Cherokee
    "S": ["5", "Ѕ", "Ꮪ"],  # Cyrillic Dze, Cherokee
    "T": ["Τ", "Т", "Ꭲ", "ꓔ"],  # Greek Tau, Cyrillic Te, Cherokee, Lisu
    "U": ["Ս", "Ꮜ"],  # Armenian, Cherokee
    "V": ["Ꮩ", "ꓦ"],  # Cherokee, Lisu
    "W": ["Ꮃ", "ꓪ"],  # Cherokee, Lisu
    "X": ["Χ", "Х", "Ꮖ"],  # Greek Chi, Cyrillic Ha, Cherokee
    "Y": ["Υ", "Ү", "Ꭹ"],  # Greek Upsilon, Cyrillic U, Cherokee
    "Z": ["Ζ", "Ꮓ"],  # Greek Zeta, Cherokee
    # Lowercase lookalikes
    "a": ["а", "ɑ"],  # Cyrillic a, Latin alpha
    "c": ["с", "ϲ"],  # Cyrillic es, Greek lunate sigma
    "d": ["ԁ"],  # Cyrillic komi de
    "e": ["е", "ҽ"],  # Cyrillic ie, Cyrillic che
    "g": ["ɡ"],  # Latin small letter script g
    "h": ["һ"],  # Cyrillic shha
    "i": ["і", "ӏ"],  # Cyrillic i, Cyrillic palochka
    "j": ["ј"],  # Cyrillic je
    "l": ["1", "I", "|", "ӏ"],  # Number one, capital I, pipe, Cyrillic palochka
    "o": ["0", "о", "ο"],  # Zero, Cyrillic o, Greek omicron
    "p": ["р"],  # Cyrillic er
    "s": ["ѕ"],  # Cyrillic dze
    "x": ["х"],  # Cyrillic ha
    "y": ["у"],  # Cyrillic u
}


@dataclass
class ScamDetectionResult:
    """Result of scam token detection."""

    is_scam: bool
    reason: Optional[str] = None
    matched_token: Optional[str] = None


def _normalize_symbol(symbol: str) -> str:
    """
    Normalize a symbol by replacing lookalike characters with their ASCII equivalents.

    This helps detect scam tokens that use Unicode lookalikes.
    """
    normalized = symbol.upper()

    # Build reverse mapping: lookalike -> legitimate character
    reverse_map = {}
    for legitimate, lookalikes in LOOKALIKE_CHARS.items():
        for lookalike in lookalikes:
            reverse_map[lookalike] = legitimate.upper()

    # Replace lookalikes with legitimate characters
    result = []
    for char in normalized:
        result.append(reverse_map.get(char, char))

    return "".join(result)


def _has_mixed_case_lookalikes(symbol: str, known_symbol: str) -> bool:
    """
    Check if a symbol uses lowercase/uppercase substitution to mimic a known token.

    For example: "DAl" (with lowercase L) trying to look like "DAI"
    """
    if len(symbol) != len(known_symbol):
        return False

    differences = 0
    for s_char, k_char in zip(symbol, known_symbol):
        if s_char != k_char:
            # Check if it's a case variation or lookalike substitution
            if s_char.upper() == k_char.upper():
                differences += 1
            elif s_char in LOOKALIKE_CHARS.get(k_char, []):
                differences += 1
            elif s_char in LOOKALIKE_CHARS.get(k_char.lower(), []):
                differences += 1
            else:
                return False

    return differences > 0


def is_scam_token(symbol: str, contract_address: Optional[str] = None) -> ScamDetectionResult:
    """
    Detect potential scam tokens using multiple heuristics.

    Checks for:
    1. Empty or missing symbols
    2. Non-ASCII characters (Unicode lookalikes like "EꓔH")
    3. Lookalike symbols that mimic known tokens (like "DAl" for "DAI")

    Args:
        symbol: The token symbol to check
        contract_address: Optional contract address for logging context

    Returns:
        ScamDetectionResult with is_scam flag, reason, and matched legitimate token if applicable
    """
    # Check 1: Empty or missing symbol
    if not symbol or not symbol.strip():
        return ScamDetectionResult(
            is_scam=True,
            reason="empty_symbol",
        )

    symbol = symbol.strip()

    # Check 2: Non-ASCII characters (Unicode lookalikes)
    if not VALID_TOKEN_SYMBOL_PATTERN.match(symbol):
        # Try to find which known token it might be impersonating
        normalized = _normalize_symbol(symbol)
        matched = normalized if normalized in KNOWN_TOKENS else None

        return ScamDetectionResult(
            is_scam=True,
            reason="non_ascii_characters",
            matched_token=matched,
        )

    # Check 3: ASCII lookalikes (e.g., "DAl" with lowercase L instead of "DAI")
    symbol_upper = symbol.upper()
    for known_token in KNOWN_TOKENS:
        if symbol_upper == known_token:
            # Exact match (case-insensitive) - not a scam
            continue

        # Check if it's a lookalike with character substitutions
        if _has_mixed_case_lookalikes(symbol, known_token):
            return ScamDetectionResult(
                is_scam=True,
                reason="lookalike_symbol",
                matched_token=known_token,
            )

        # Check if normalized version matches a known token
        normalized = _normalize_symbol(symbol)
        if normalized == known_token and symbol.upper() != known_token:
            return ScamDetectionResult(
                is_scam=True,
                reason="lookalike_symbol",
                matched_token=known_token,
            )

    # No scam indicators found
    return ScamDetectionResult(is_scam=False)
