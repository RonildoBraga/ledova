import logging
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.utils import timezone
from web3 import Web3

from shared.db import atomic
from tokens.models import FormerHolder, ShareIssuance, ShareToken
from tokens.models.choices import IDENTITY_RECORDED, IDENTITY_STAMPED, IDENTITY_UNKNOWN
from tokens.services.register import (
    IDENTITY_BY_HOLDER_TYPE,
    ZERO_ADDRESS,
    _deployment_block,
    chain_service,
)
from whitelist.models import HolderType
from whitelist.services.identity import UNIDENTIFIED, identities_for

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(hours=24)
MINIMUM_RETENTION_DAYS = 2557


def retention_cutoff(now=None):
    days = settings.FORMER_MEMBER_RETENTION_DAYS
    if days < MINIMUM_RETENTION_DAYS:
        raise ImproperlyConfigured("Former-member retention cannot be shorter than 2557 days.")
    return (now or timezone.now()).date() - timedelta(days=days)


def cessations_in(entries) -> list:
    balances = defaultdict(int)
    cessations = []
    seen = set()
    for entry in sorted(entries, key=lambda item: (item["block_number"], item["log_index"])):
        event = (entry["block_number"], entry["log_index"])
        if event in seen:
            raise ValueError("Transfer history repeats an event.")
        seen.add(event)
        sender = Web3.to_checksum_address(entry["from"])
        recipient = Web3.to_checksum_address(entry["to"])
        value = entry["value"]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("Transfer history contains an invalid share quantity.")
        if sender == recipient:
            continue
        if _is_an_account(sender) and balances[sender] < value:
            raise ValueError("Transfer history is incomplete: a sender spends shares it never received.")
        if _is_an_account(recipient):
            balances[recipient] += value
        if _is_an_account(sender):
            before = balances[sender]
            balances[sender] = before - value
            if before > 0 and balances[sender] <= 0:
                cessations.append({"address": sender, "block_number": entry["block_number"], "shares": before})
    return cessations


def _is_an_account(address) -> bool:
    return bool(address) and address.lower() != ZERO_ADDRESS


def _particulars(address, identities, stamps) -> dict:
    identity = identities.get(address.lower(), UNIDENTIFIED)
    if identity.holder_type == HolderType.UNIDENTIFIED.value:
        stamp = stamps.get(address.lower())
        if stamp:
            return {
                "name": stamp["name"],
                "residential_address": stamp["residential_address"],
                "identity_source": IDENTITY_STAMPED if stamp["stamped_at"] is not None else IDENTITY_RECORDED,
            }
        return {"name": "", "residential_address": "", "identity_source": IDENTITY_UNKNOWN}
    return {
        "name": identity.name,
        "residential_address": identity.residential_address,
        "identity_source": IDENTITY_BY_HOLDER_TYPE.get(identity.holder_type, IDENTITY_STAMPED),
    }


def former_members_of(token: ShareToken):
    return FormerHolder.objects.filter(token=token).order_by("-ceased_on", "wallet_address")


def fold_former_holders(token: ShareToken, reader=None) -> dict:
    retention_cutoff()
    reader = reader or chain_service()
    head = reader.head_block()
    entries = reader.transfer_entries(token.contract_address, _deployment_block(token, reader), head)
    cessations = cessations_in(entries)

    dates = {}
    for cessation in cessations:
        block = cessation["block_number"]
        if block not in dates:
            dates[block] = reader.block_date(block)
    cutoff = retention_cutoff()
    retained = {}
    for cessation in cessations:
        block = cessation["block_number"]
        if dates[block] >= cutoff:
            retained[(cessation["address"], block)] = cessation
    existing = set(FormerHolder.objects.filter(token=token).values_list("wallet_address", "ceased_at_block"))
    missing = {key: value for key, value in retained.items() if key not in existing}
    identities = identities_for([address for address, _block in missing])
    stamps = {
        block: ShareIssuance.objects.filter_by_token(token)
        .filter(
            Q(identity_stamped_at__date__lte=dates[block])
            | Q(identity_stamped_at__isnull=True, created_at__date__lte=dates[block])
        )
        .latest_identity_stamps()
        for block in {block for _address, block in missing}
    }
    written = 0
    with atomic():
        locked = ShareToken.objects.select_for_update().get(pk=token.pk)
        if locked.former_holders_block is not None and head < locked.former_holders_block:
            return {"cessations": len(cessations), "written": 0, "block": locked.former_holders_block}
        for (address, block), cessation in missing.items():
            if dates[block] < retention_cutoff():
                continue
            _, created = FormerHolder.objects.get_or_create(
                token=locked,
                wallet_address=address,
                ceased_at_block=block,
                defaults={
                    "ceased_on": dates[block],
                    "shares_at_cessation": cessation["shares"],
                    **_particulars(address, identities, stamps[block]),
                },
            )
            written += int(created)
        ShareToken.objects.filter(pk=locked.pk).update(
            former_holders_folded_at=timezone.now(), former_holders_block=head
        )
    logger.info(f"{token.symbol}: {len(cessations)} cessations read to block {head}, {written} new")
    return {"cessations": len(cessations), "written": written, "block": head}


def fold_is_stale(token: ShareToken, now=None) -> bool:
    if token.former_holders_folded_at is None:
        return True
    return (now or timezone.now()) - token.former_holders_folded_at > STALE_AFTER


def purge_former_holders(now=None) -> int:
    cutoff = retention_cutoff(now)
    removed, _ = FormerHolder.objects.filter(ceased_on__lt=cutoff).delete()
    if removed:
        logger.info(f"Removed {removed} former-member records that passed the seven-year clock")
    return removed
