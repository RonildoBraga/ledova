import hashlib
import json
from collections import Counter

from django.core.serializers.json import DjangoJSONEncoder

from assets.models import AssetChainDeployment
from blockchain.models import BlockchainTransaction, TransactionType
from tokens.models import (
    CapitalIncreaseRequest,
    MintRequest,
    NAVUpdate,
    ShareIssuance,
    ShareIssuanceRequest,
    ShareToken,
    SwapOrder,
    YieldToken,
)
from whitelist.models import WhitelistEntry

OPERATOR_TYPES = (
    TransactionType.WHITELIST_ADD,
    TransactionType.WHITELIST_REMOVE,
    TransactionType.WHITELIST_UPDATE,
    TransactionType.TOKEN_DEPLOY,
    TransactionType.TOKEN_MINT,
    TransactionType.TOKEN_BURN,
    TransactionType.STABLECOIN_MINT,
    TransactionType.STABLECOIN_BURN,
    TransactionType.YIELD_TOKEN_MINT,
    TransactionType.YIELD_TOKEN_NAV_UPDATE,
    TransactionType.ATOMIC_SWAP,
    TransactionType.SHARE_TOKEN_DEPLOY,
    TransactionType.CONTRACT_DEPLOY,
    TransactionType.OTHER,
)
ARGUMENT_KEYS = (
    "to",
    "amount",
    "investor",
    "newNavPerToken",
    "newReserveValue",
    "authorizedShares",
    "tokenOwner",
    "issuerWallet",
    "newAuthorizedShares",
    "seller",
    "buyer",
    "shareToken",
    "paymentToken",
    "shareAmount",
    "paymentAmount",
    "nonce",
)
JOURNAL_KEYS = ("id", "tx_hash", "raw_transaction", "signed_at", "reverted", "abandoned")


def _json(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":")))


def _digest(value):
    return hashlib.sha256(json.dumps(_json(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _rows(model, *fields):
    return {
        str(row["uuid"]): _json(row) for row in model.objects.order_by("uuid").values("uuid", "updated_at", *fields)
    }


def _source(model, row, **context):
    return {"model": model._meta.label, "uuid": row["uuid"], "entry_key": "row", "row": row, **context}


def _issuances(rows, requests, capitals, tokens):
    result = []
    for original in rows.values():
        row = {key: value for key, value in original.items() if key != "mint_journal"}
        journal = original["mint_journal"]
        matching = [
            request
            for request in requests.values()
            if row["idempotency_key"] == f"issuance-request:{request['uuid']}"
            or request["executed_issuance_id"] == row["uuid"]
        ]
        capital_links = [
            request["uuid"] for request in capitals.values() if request["executed_issuance_id"] == row["uuid"]
        ]
        entries = journal if isinstance(journal, list) and journal else [None]
        ids = Counter(
            entry.get("id") for entry in entries if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        )
        shape = (
            "entries"
            if isinstance(journal, list) and journal
            else "empty" if journal == [] else "missing" if journal is None else "invalid"
        )
        for index, entry in enumerate(entries):
            item = _source(
                ShareIssuance,
                row,
                kind="share_mint",
                token=tokens.get(row["token_id"]),
                request_candidates=matching,
                capital_links=capital_links,
                journal_shape=shape,
                journal_digest=_digest(journal),
                is_current_entry=index == len(entries) - 1,
                entry_keys=sorted(entry) if isinstance(entry, dict) else [],
                journal_entry=(
                    {key: entry[key] for key in JOURNAL_KEYS if key in entry} if isinstance(entry, dict) else None
                ),
                entry_digest=_digest(entry),
                attempt_id_unique=isinstance(entry, dict)
                and isinstance(entry.get("id"), str)
                and ids[entry["id"]] == 1,
            )
            item["entry_key"] = f"journal:{index}" if shape == "entries" else "journal"
            result.append(item)
    return result


def read_legacy_outgoing_sources():
    tokens = _rows(
        ShareToken,
        "contract_address",
        "chain",
        "decimals",
        "total_supply",
        "status",
        "deployment_tx_hash",
        "deployment_transaction_id",
    )
    requests = _rows(ShareIssuanceRequest, "token_id", "recipient_address", "amount", "status", "executed_issuance_id")
    capitals = _rows(
        CapitalIncreaseRequest,
        "token_id",
        "additional_shares",
        "new_authorized_total",
        "status",
        "executed_issuance_id",
    )
    issuances = _rows(
        ShareIssuance,
        "token_id",
        "recipient_address",
        "amount",
        "status",
        "tx_hash",
        "mint_journal",
        "idempotency_key",
        "transaction_id",
    )
    mints = _rows(
        MintRequest, "settlement_asset_id", "yield_token_id", "recipient_address", "amount", "status", "transaction_id"
    )
    navs = _rows(
        NAVUpdate, "yield_token_id", "old_nav_per_token", "new_nav_per_token", "total_reserve_value", "transaction_id"
    )
    yields = _rows(YieldToken, "contract_address", "decimals")
    deployments = _rows(AssetChainDeployment, "asset_id", "chain", "contract_address", "decimals")
    swaps = _rows(
        SwapOrder,
        "share_token_id",
        "payment_asset_id",
        "seller_address",
        "buyer_address",
        "share_amount",
        "payment_amount",
        "nonce",
        "order_hash",
        "expires_at",
        "status",
        "tx_hash",
        "transaction_id",
    )
    whitelist = _rows(WhitelistEntry, "address", "wallet__address", "status", "add_tx_hash", "remove_tx_hash")
    registry = {
        ShareToken._meta.label: tokens,
        ShareIssuanceRequest._meta.label: requests,
        ShareIssuance._meta.label: {
            key: {field: value for field, value in row.items() if field != "mint_journal"}
            for key, row in issuances.items()
        },
        CapitalIncreaseRequest._meta.label: capitals,
        MintRequest._meta.label: mints,
        NAVUpdate._meta.label: navs,
        SwapOrder._meta.label: swaps,
        WhitelistEntry._meta.label: whitelist,
    }
    transactions = list(
        BlockchainTransaction.objects.filter(tx_type__in=OPERATOR_TYPES)
        .order_by("uuid")
        .values(
            "uuid",
            "updated_at",
            "tx_type",
            "status",
            "tx_hash",
            "from_address",
            "to_address",
            "value",
            "nonce",
            "function_name",
            "function_args",
            "related_model",
            "related_uuid",
        )
    )
    result = _issuances(issuances, requests, capitals, tokens)
    for request in requests.values():
        linked = any(
            row["idempotency_key"] == f"issuance-request:{request['uuid']}"
            or row["uuid"] == request["executed_issuance_id"]
            for row in issuances.values()
        )
        if not linked:
            result.append(
                _source(ShareIssuanceRequest, request, kind="metadata", token=tokens.get(request["token_id"]))
            )
    projections = {str(row["uuid"]): row for row in transactions}
    for original in transactions:
        row = _json(original)
        args = row["function_args"]
        row["function_args_digest"] = _digest(args)
        row["function_args"] = (
            {key: args[key] for key in ARGUMENT_KEYS if key in args} if isinstance(args, dict) else None
        )
        related = registry.get(row["related_model"], {}).get(row["related_uuid"])
        result.append(_source(BlockchainTransaction, row, kind="metadata", related=related))
    for model, rows, link in (
        (ShareToken, tokens, "deployment_transaction_id"),
        (CapitalIncreaseRequest, capitals, None),
        (MintRequest, mints, "transaction_id"),
        (NAVUpdate, navs, "transaction_id"),
        (SwapOrder, swaps, "transaction_id"),
        (WhitelistEntry, whitelist, None),
    ):
        for row in rows.values():
            related_transactions = sorted(
                str(tx["uuid"])
                for tx in transactions
                if tx["related_model"] == model._meta.label and str(tx["related_uuid"]) == row["uuid"]
            )
            context = {
                "related_transactions": related_transactions,
                "projection_exists": bool(link and row[link] in projections),
            }
            if "token_id" in row or "share_token_id" in row:
                context["token"] = tokens.get(row.get("token_id", row.get("share_token_id")))
            if "yield_token_id" in row:
                context["yield_token"] = yields.get(row["yield_token_id"])
            if row.get("settlement_asset_id") or row.get("payment_asset_id"):
                asset_id = row.get("settlement_asset_id") or row["payment_asset_id"]
                context["asset_deployments"] = [item for item in deployments.values() if item["asset_id"] == asset_id]
            result.append(_source(model, row, kind="metadata", **context))
    return tuple(result)
