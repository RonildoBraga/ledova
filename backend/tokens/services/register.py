import logging

from integrations.base_chain.exceptions import BaseChainConnectionError
from shared.utils import csv_cell
from tokens.models import ShareIssuance
from tokens.services.share_token_service import ShareTokenService
from whitelist.models import HolderType
from whitelist.services.identity import UNIDENTIFIED, identities_for

logger = logging.getLogger(__name__)

SOURCE_CHAIN = "blockchain"
SOURCE_ALLOTMENTS = "issuances"

SOURCE_LABELS = {
    SOURCE_CHAIN: "Confirmed on chain",
    SOURCE_ALLOTMENTS: "Allotment record, not confirmed on chain",
}

REGISTER_HEADERS = [
    "Name",
    "Residential address",
    "Wallet address",
    "Holder type",
    "Class",
    "Shares held",
    "Balance source",
    "Date entered",
    "Whitelist status",
    "Amount paid",
]

NO_WHITELIST_ENTRY = "No whitelist entry"

API_FIELDS = ("address", "name", "balance", "percentage", "source", "holder_type", "entered_on", "share_class")


def chain_service():
    try:
        return ShareTokenService()
    except BaseChainConnectionError as exc:
        logger.error(f"Register could not reach the chain: {exc}")
        return None


def _allotments(token) -> dict:
    grouped = {}
    issuances = ShareIssuance.objects.filter_by_token(token).completed().with_subscription().order_by("created_at")
    for issuance in issuances:
        row = grouped.setdefault(
            issuance.recipient_address, {"shares": 0, "entered_on": None, "paid": None, "unbacked": 0}
        )
        row["shares"] += _amount(issuance)
        moment = issuance.completed_at or issuance.created_at
        if row["entered_on"] is None or (moment is not None and moment < row["entered_on"]):
            row["entered_on"] = moment
        subscription = _subscription(issuance)
        if subscription is None:
            row["unbacked"] += 1
        else:
            row["paid"] = (row["paid"] or 0) + subscription.money_held
    return grouped


def _amount(issuance) -> int:
    try:
        return int(issuance.amount)
    except (TypeError, ValueError):
        return 0


def _subscription(issuance):
    request = getattr(issuance, "shareissuancerequest", None)
    if request is None:
        return None
    return getattr(request, "subscription", None)


def _chain_balances(token, addresses, reader):
    if not token.is_deployed or reader is None or not addresses:
        return None
    balances = {}
    for address in addresses:
        try:
            balances[address] = reader.get_token_balance(token.contract_address, address)
        except Exception as exc:
            logger.error(
                f"Register could not read the balance of {address} on {token.symbol}: {exc}; discarding the whole "
                f"chain read and falling back to the allotment record for every holder"
            )
            return None
    return balances


def _register(token, reader) -> list[dict]:
    allotments = _allotments(token)
    if not allotments:
        return []
    fallback_names = ShareIssuance.objects.filter_by_token(token).unique_holders_with_names()
    identities = identities_for(list(allotments))
    balances = _chain_balances(token, list(allotments), reader)
    source = SOURCE_ALLOTMENTS if balances is None else SOURCE_CHAIN

    rows = []
    for address, allotment in allotments.items():
        balance = allotment["shares"] if balances is None else balances[address]
        if not balance or balance <= 0:
            continue
        identity = identities.get(address.lower(), UNIDENTIFIED)
        rows.append(
            {
                "address": address,
                "name": identity.name or fallback_names.get(address) or None,
                "balance": str(balance),
                "source": source,
                "holder_type": identity.holder_type,
                "holder_type_display": HolderType(identity.holder_type).label,
                "entered_on": allotment["entered_on"],
                "share_class": token.symbol,
                "whitelist_status": identity.whitelist_status,
                "residential_address": identity.residential_address,
                "amount_paid": None if allotment["unbacked"] else allotment["paid"],
            }
        )

    total = sum(int(row["balance"]) for row in rows)
    for row in rows:
        row["percentage"] = round(int(row["balance"]) / total * 100, 2) if total else 0
    rows.sort(key=lambda row: int(row["balance"]), reverse=True)
    return rows


def token_register(token, service=None) -> list[dict]:
    return _register(token, service if service is not None else chain_service())


def api_holders(rows) -> list[dict]:
    return [{field: row[field] for field in API_FIELDS} for row in rows]


def export_rows(token, requested_by) -> list[list]:
    rows = token_register(token)
    logger.info(
        f"Register export of {token.symbol} for company {token.company_id}: "
        f"{len(rows)} rows, requested by user {getattr(requested_by, 'pk', None)}"
    )
    if any(row["source"] != SOURCE_CHAIN for row in rows):
        logger.warning(
            f"Register export of {token.symbol} for company {token.company_id} is not confirmed on chain; "
            f"every row carries {SOURCE_LABELS[SOURCE_ALLOTMENTS]}"
        )
    return [_csv_row(row) for row in rows]


def _csv_row(row) -> list:
    entered_on = row["entered_on"]
    return [
        csv_cell(value)
        for value in (
            row["name"] or "",
            row["residential_address"],
            row["address"],
            row["holder_type_display"],
            row["share_class"],
            row["balance"],
            SOURCE_LABELS[row["source"]],
            entered_on.date().isoformat() if entered_on else "",
            row["whitelist_status"] or NO_WHITELIST_ENTRY,
            "" if row["amount_paid"] is None else f"{row['amount_paid']:.2f}",
        )
    ]
