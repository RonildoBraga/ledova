import logging
from decimal import Decimal

from integrations.base_chain.exceptions import BaseChainConnectionError
from shared.utils import csv_cell
from tokens.exceptions import RegisterUnavailableException
from tokens.models import ShareIssuance
from tokens.models.choices import (
    IDENTITY_LABELS,
    IDENTITY_LIVE,
    IDENTITY_NONE,
    IDENTITY_RECORDED,
    IDENTITY_STAMPED,
    IDENTITY_TREASURY_LABEL,
    IDENTITY_UNRESOLVABLE,
)
from tokens.services.share_token_service import ShareTokenService
from whitelist.models import HolderType
from whitelist.services.identity import UNIDENTIFIED, identities_for

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")

SOURCE_CHAIN = "blockchain"

SOURCE_LABELS = {
    SOURCE_CHAIN: "Confirmed on chain",
}

ZERO_ADDRESS = "0x" + "0" * 40

EMPTY_ALLOTMENT = {"shares": 0, "entered_on": None, "paid": ZERO, "backed": 0, "unbacked": 0}


IDENTITY_BY_HOLDER_TYPE = {
    HolderType.MEMBER.value: IDENTITY_LIVE,
    HolderType.TREASURY.value: IDENTITY_TREASURY_LABEL,
    HolderType.AMBIGUOUS.value: IDENTITY_UNRESOLVABLE,
    HolderType.UNIDENTIFIED.value: IDENTITY_NONE,
}


def identity_source_label(source, stamped_at) -> str:
    if source != IDENTITY_STAMPED:
        return IDENTITY_LABELS[source]
    return f"Stamped at allotment on {stamped_at.date().isoformat()}"


ISSUED_SUPPLY_ROW = "Issued supply"
LISTED_TOTAL_ROW = "Held by listed holders"
DISCREPANCY_ROW = "Not held by any listed holder"
FORMER_MEMBERS_HEADING = "Former members (retained under s169(3) of the Corporations Act)"
FORMER_MEMBER_HEADERS = [
    "Name",
    "Residential address",
    "Wallet address",
    "Shares held on ceasing",
    "Date ceased",
    "Identity source",
    "Identity recorded at",
]
AS_AT_ROW = "As at"
NEVER_FOLDED = "never read"
STALE = "stale"

REGISTER_HEADERS = [
    "Name",
    "Residential address",
    "Wallet address",
    "Holder type",
    "Class",
    "Shares held",
    "Percentage of issued supply",
    "Balance source",
    "Identity source",
    "Date entered",
    "Whitelist status",
    "Amount paid",
]

NO_WHITELIST_ENTRY = "No whitelist entry"

API_FIELDS = (
    "address",
    "name",
    "balance",
    "percentage",
    "source",
    "holder_type",
    "entered_on",
    "share_class",
    "identity_source",
)


def chain_service():
    try:
        return ShareTokenService()
    except BaseChainConnectionError as exc:
        logger.error(f"Register could not reach the chain: {exc}")
        raise RegisterUnavailableException(
            f"{RegisterUnavailableException.default_detail} The chain was unreachable when this request ran."
        ) from exc


def _deployment_block(token, reader) -> int:
    transaction = token.deployment_transaction
    if transaction is not None and transaction.block_number is not None:
        return transaction.block_number
    if token.deployment_tx_hash:
        try:
            return reader.deployment_block(token.deployment_tx_hash)
        except Exception as exc:
            logger.error(f"Register could not read the deployment block of {token.symbol}: {exc}")
            raise RegisterUnavailableException(
                f"{RegisterUnavailableException.default_detail} The deployment block of {token.symbol} could not "
                f"be read from transaction {token.deployment_tx_hash}."
            ) from exc
    raise RegisterUnavailableException(
        f"{RegisterUnavailableException.default_detail} {token.symbol} records no deployment block and no "
        f"deployment transaction, so the transfer history has no start and the holder set cannot be built."
    )


def _holder_addresses(token, reader) -> list:
    allotments = _allotments(token)
    addresses = set(allotments)
    try:
        participants = reader.transfer_participants(token.contract_address, _deployment_block(token, reader))
    except RegisterUnavailableException:
        raise
    except Exception as exc:
        logger.error(f"Register could not read the transfer history of {token.symbol}: {exc}")
        raise RegisterUnavailableException(
            f"{RegisterUnavailableException.default_detail} The transfer history of {token.symbol} could not be "
            f"read."
        ) from exc
    addresses.update(participants)
    addresses.discard(ZERO_ADDRESS)
    addresses.discard(ZERO_ADDRESS.lower())
    return sorted(addresses), allotments


def _issued_supply(token, reader) -> int:
    try:
        return reader.share_supply(token.contract_address)[1]
    except Exception as exc:
        logger.error(f"Register could not read the issued supply of {token.symbol}: {exc}")
        raise RegisterUnavailableException(
            f"{RegisterUnavailableException.default_detail} The issued supply of {token.symbol} could not be " f"read."
        ) from exc


def _allotments(token) -> dict:
    grouped = {}
    issuances = ShareIssuance.objects.filter_by_token(token).completed().with_subscription().order_by("created_at")
    for issuance in issuances:
        row = grouped.setdefault(
            issuance.recipient_address, {"shares": 0, "entered_on": None, "paid": ZERO, "backed": 0, "unbacked": 0}
        )
        shares = _amount(issuance)
        row["shares"] += shares
        moment = issuance.completed_at or issuance.created_at
        if row["entered_on"] is None or (moment is not None and moment < row["entered_on"]):
            row["entered_on"] = moment
        backing = _backing(issuance, shares)
        if backing is None:
            row["unbacked"] += 1
        else:
            row["paid"] += backing
            row["backed"] += shares
    return grouped


def _backing(issuance, shares):
    subscription = _subscription(issuance)
    if subscription is None or subscription.allotment_quantity != shares:
        return None
    backing = subscription.money_backing_shares
    return backing if backing > ZERO else None


def _amount_paid(allotment, balance):
    if allotment["unbacked"] or allotment["backed"] != int(balance):
        return None
    return allotment["paid"]


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
    balances = {}
    for address in addresses:
        try:
            balances[address] = reader.get_token_balance(token.contract_address, address)
        except Exception as exc:
            logger.error(f"Register could not read the balance of {address} on {token.symbol}: {exc}")
            raise RegisterUnavailableException(
                f"{RegisterUnavailableException.default_detail} The balance of {address} on {token.symbol} could "
                f"not be read."
            ) from exc
    return balances


def _register(token, reader) -> tuple[list[dict], int]:
    addresses, allotments = _holder_addresses(token, reader)
    if not addresses:
        return [], 0
    stamps = ShareIssuance.objects.filter_by_token(token).latest_identity_stamps()
    identities = identities_for(addresses)
    balances = _chain_balances(token, addresses, reader)
    issued = _issued_supply(token, reader)
    source = SOURCE_CHAIN

    rows = []
    for address in addresses:
        allotment = allotments.get(address, EMPTY_ALLOTMENT)
        balance = balances[address]
        if not balance or balance <= 0:
            continue
        identity = identities.get(address.lower(), UNIDENTIFIED)
        stamp = stamps.get(address.lower())
        unidentified = identity.holder_type == HolderType.UNIDENTIFIED.value
        resolved_stamp = stamp if stamp and stamp["stamped_at"] else None
        if unidentified and resolved_stamp:
            name = resolved_stamp["name"]
            residential_address = resolved_stamp["residential_address"]
            holder_type = HolderType.MEMBER.value
            identity_source, stamped_at = IDENTITY_STAMPED, resolved_stamp["stamped_at"]
        elif unidentified:
            name = stamp["name"] if stamp else ""
            residential_address = ""
            holder_type = identity.holder_type
            identity_source = IDENTITY_RECORDED if name else IDENTITY_NONE
            stamped_at = None
        else:
            name = identity.name
            residential_address = identity.residential_address
            holder_type = identity.holder_type
            identity_source = IDENTITY_BY_HOLDER_TYPE[holder_type]
            stamped_at = None
        rows.append(
            {
                "address": address,
                "name": name or None,
                "balance": str(balance),
                "source": source,
                "holder_type": holder_type,
                "holder_type_display": HolderType(holder_type).label,
                "identity_source": identity_source_label(identity_source, stamped_at),
                "entered_on": allotment["entered_on"],
                "share_class": token.symbol,
                "whitelist_status": identity.whitelist_status,
                "residential_address": residential_address,
                "amount_paid": _amount_paid(allotment, balance),
            }
        )

    for row in rows:
        row["percentage"] = round(int(row["balance"]) / issued * 100, 2) if issued else 0
    rows.sort(key=lambda row: int(row["balance"]), reverse=True)
    return rows, issued - sum(int(row["balance"]) for row in rows)


def token_register(token, service=None) -> tuple[list[dict], int]:
    return _register(token, service if service is not None else chain_service())


def api_holders(rows) -> list[dict]:
    return [{field: row[field] for field in API_FIELDS} for row in rows]


def _summary_rows(rows, discrepancy) -> list[list]:
    listed = sum(int(row["balance"]) for row in rows)
    summary = [
        [ISSUED_SUPPLY_ROW, str(listed + discrepancy)],
        [LISTED_TOTAL_ROW, str(listed)],
    ]
    if discrepancy:
        summary.append([DISCREPANCY_ROW, str(discrepancy)])
    return summary


def export_rows(token, requested_by) -> list[list]:
    rows, discrepancy = token_register(token)
    logger.info(
        f"Register export of {token.symbol} for company {token.company_id}: "
        f"{len(rows)} rows, requested by user {getattr(requested_by, 'pk', None)}"
    )
    if discrepancy:
        logger.warning(
            f"Register export of {token.symbol} for company {token.company_id} does not account for the whole "
            f"issued supply: {discrepancy} shares are held by nobody the register lists"
        )
    return [_csv_row(row) for row in rows] + [[]] + _summary_rows(rows, discrepancy) + former_member_rows(token)


def former_member_rows(token) -> list[list]:
    from tokens.services.former_holders import fold_is_stale, former_members_of

    rows = [
        [
            csv_cell(row.name),
            csv_cell(row.residential_address),
            csv_cell(row.wallet_address),
            csv_cell(str(row.shares_at_cessation)),
            csv_cell(row.ceased_on.isoformat()),
            csv_cell(
                "Profile when the cessation was recorded"
                if row.identity_source == IDENTITY_LIVE
                else IDENTITY_LABELS.get(row.identity_source, row.identity_source)
            ),
            csv_cell(row.created_at.isoformat()),
        ]
        for row in former_members_of(token)
    ]
    return [[], [FORMER_MEMBERS_HEADING], FORMER_MEMBER_HEADERS, *rows, _as_at_row(token, fold_is_stale(token))]


def _as_at_row(token, stale: bool) -> list:
    if token.former_holders_folded_at is None:
        return [AS_AT_ROW, NEVER_FOLDED, STALE]
    reached = "" if token.former_holders_block is None else f"block {token.former_holders_block}"
    read_at = token.former_holders_folded_at.isoformat()
    return [AS_AT_ROW, read_at, reached, STALE] if stale else [AS_AT_ROW, read_at, reached]


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
            f"{row['percentage']}%",
            SOURCE_LABELS[row["source"]],
            row["identity_source"],
            entered_on.date().isoformat() if entered_on else "",
            row["whitelist_status"] or NO_WHITELIST_ENTRY,
            "" if row["amount_paid"] is None else f"{row['amount_paid']:.2f}",
        )
    ]
