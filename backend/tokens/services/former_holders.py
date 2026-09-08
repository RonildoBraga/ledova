import logging
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from tokens.models import FormerHolder, ShareToken
from tokens.models.choices import IDENTITY_STAMPED, IDENTITY_UNKNOWN
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


def cessations_in(entries) -> list:
    balances = defaultdict(int)
    cessations = []
    for entry in entries:
        sender, recipient, value = entry["from"], entry["to"], entry["value"]
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


def _particulars(address, identities) -> dict:
    identity = identities.get(address.lower(), UNIDENTIFIED)
    if identity.holder_type == HolderType.UNIDENTIFIED.value:
        return {"name": "", "residential_address": "", "identity_source": IDENTITY_UNKNOWN}
    return {
        "name": identity.name,
        "residential_address": identity.residential_address,
        "identity_source": IDENTITY_BY_HOLDER_TYPE.get(identity.holder_type, IDENTITY_STAMPED),
    }


def former_members_of(token: ShareToken):
    return FormerHolder.objects.filter(token=token).order_by("-ceased_on", "wallet_address")


def fold_former_holders(token: ShareToken, reader=None) -> dict:
    reader = reader or chain_service()
    head = reader.head_block()
    entries = reader.transfer_entries(token.contract_address, _deployment_block(token, reader), head)
    cessations = cessations_in(entries)

    identities = identities_for([cessation["address"] for cessation in cessations])
    dates = {}
    written = 0
    for cessation in cessations:
        block = cessation["block_number"]
        if block not in dates:
            dates[block] = reader.block_date(block)
        _, created = FormerHolder.objects.get_or_create(
            token=token,
            wallet_address=cessation["address"],
            ceased_at_block=block,
            defaults={
                "ceased_on": dates[block],
                "shares_at_cessation": cessation["shares"],
                **_particulars(cessation["address"], identities),
            },
        )
        written += int(created)

    ShareToken.objects.filter(pk=token.pk).update(former_holders_folded_at=timezone.now(), former_holders_block=head)
    logger.info(f"{token.symbol}: {len(cessations)} cessations read to block {head}, {written} new")
    return {"cessations": len(cessations), "written": written, "block": head}


def fold_is_stale(token: ShareToken, now=None) -> bool:
    if token.former_holders_folded_at is None:
        return True
    return (now or timezone.now()) - token.former_holders_folded_at > STALE_AFTER


def purge_former_holders(now=None) -> int:
    cutoff = (now or timezone.now()).date() - timedelta(days=settings.FORMER_MEMBER_RETENTION_DAYS)
    removed, _ = FormerHolder.objects.filter(ceased_on__lt=cutoff).delete()
    if removed:
        logger.info(f"Removed {removed} former-member records that passed the seven-year clock")
    return removed
