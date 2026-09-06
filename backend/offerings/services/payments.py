import re
import secrets
from decimal import Decimal

from offerings.exceptions import SubscriptionRefusedException
from offerings.models.subscription import MAX_REFERENCE_LENGTH, SettlementRail
from operators.models import Operator
from operators.settlement import require_deployment

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
REFERENCE_CODE_LENGTH = 8
REFERENCE_ATTEMPTS = 6
CONFUSABLE = str.maketrans({"O": "0", "I": "1", "L": "1"})

NO_REFERENCE_PREFIX = (
    "The operator has no payment reference prefix configured, so a subscription reference cannot be issued. "
    "Set Operator.payment_reference_prefix first."
)
REFERENCES_EXHAUSTED = "Could not find an unused payment reference after {attempts} attempts."
BANK_NOT_CONFIGURED = (
    "The operator has no bank account configured, so a bank-transfer instruction cannot be issued. "
    "Set the account name, BSB and account number on the operator row first."
)
WALLET_NOT_CONFIGURED = (
    "The operator has no receiving wallet configured, so a stablecoin instruction cannot be issued. "
    "Set Operator.receiving_wallet_address first."
)
AMOUNT_NOT_REPRESENTABLE = (
    "{amount} {currency} cannot be expressed in whole units of {symbol}, which carries {decimals} decimals on "
    "{chain}. Price the offering to the settlement asset's precision."
)


def normalize_reference(text: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", (text or "").upper()).translate(CONFUSABLE)


def _code() -> str:
    return "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(REFERENCE_CODE_LENGTH))


def generate_reference(operator: Operator) -> str:
    from offerings.models import Subscription

    prefix = normalize_reference(operator.payment_reference_prefix)
    if not prefix:
        raise SubscriptionRefusedException(NO_REFERENCE_PREFIX)
    for _ in range(REFERENCE_ATTEMPTS):
        reference = f"{prefix}{_code()}"[:MAX_REFERENCE_LENGTH]
        if not Subscription.objects.filter(reference=reference).exists():
            return reference
    raise SubscriptionRefusedException(REFERENCES_EXHAUSTED.format(attempts=REFERENCE_ATTEMPTS))


def raw_settlement_amount(amount: Decimal, asset) -> tuple[int, object]:
    deployment = require_deployment(asset)
    scaled = Decimal(amount).scaleb(deployment.decimals)
    if scaled != scaled.to_integral_value():
        raise SubscriptionRefusedException(
            AMOUNT_NOT_REPRESENTABLE.format(
                amount=amount,
                currency="AUD",
                symbol=asset.symbol,
                decimals=deployment.decimals,
                chain=deployment.chain,
            )
        )
    return int(scaled), deployment


def build_instruction(subscription) -> dict:
    operator = Operator.get()
    common = {
        "rail": subscription.settlement_rail,
        "rail_display": subscription.get_settlement_rail_display(),
        "reference": subscription.reference,
        "amount_due": str(subscription.amount_due),
        "currency": subscription.offering.price_currency,
        "payment_due_at": subscription.payment_due_at,
        "issued_at": subscription.payment_instruction_issued_at,
        "payee": operator.legal_name or operator.name,
    }
    if subscription.settlement_rail == SettlementRail.STABLECOIN:
        return {**common, **_stablecoin_fields(subscription, operator)}
    return {**common, **_bank_fields(operator)}


def _bank_fields(operator: Operator) -> dict:
    if not (operator.bank_account_name and operator.bank_bsb and operator.bank_account_number):
        raise SubscriptionRefusedException(BANK_NOT_CONFIGURED)
    return {
        "bank_account_name": operator.bank_account_name,
        "bank_bsb": operator.bank_bsb,
        "bank_account_number": operator.bank_account_number,
    }


def _stablecoin_fields(subscription, operator: Operator) -> dict:
    if not operator.receiving_wallet_address:
        raise SubscriptionRefusedException(WALLET_NOT_CONFIGURED)
    raw, deployment = raw_settlement_amount(subscription.amount_due, subscription.settlement_asset)
    return {
        "receiving_wallet_address": operator.receiving_wallet_address,
        "chain": deployment.chain,
        "asset_symbol": subscription.settlement_asset.symbol,
        "contract_address": deployment.contract_address,
        "decimals": deployment.decimals,
        "settlement_amount": str(subscription.settlement_amount if subscription.settlement_amount else raw),
    }
