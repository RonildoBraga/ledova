import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from assets.models import Asset, AssetSnapshot
from blockchain.models import TransactionType
from integrations.base_chain.exceptions import (
    BaseChainContractError,
    BaseChainTransactionError,
)
from shared.utils.logging_utils import LoggingContext
from tokens.exceptions import (
    YieldTokenContractNotConfiguredException,
    YieldTokenMintFailedException,
    YieldTokenNAVUpdateFailedException,
)
from tokens.models import NAVUpdate, YieldToken
from tokens.services.base_token_service import BaseTokenService

logger = logging.getLogger(__name__)


class YieldTokenService(BaseTokenService):

    contract_name = "AUSG"
    not_configured_exception = YieldTokenContractNotConfiguredException
    mint_failed_exception = YieldTokenMintFailedException
    mint_tx_type = TransactionType.YIELD_TOKEN_MINT

    def get_nav_per_token(self) -> int:
        return self.contract.functions.navPerToken().call()

    def get_total_reserve_value(self) -> int:
        return self.contract.functions.totalReserveValue().call()

    def get_last_nav_update(self) -> int:
        return self.contract.functions.lastNavUpdate().call()

    def is_nav_updater(self, address: str) -> bool:
        checksum_address = self.chain_client.to_checksum_address(address)
        return self.contract.functions.navUpdaters(checksum_address).call()

    def get_nav_info(self) -> dict:
        decimals = self.get_decimals()
        nav_raw = self.get_nav_per_token()
        reserve_raw = self.get_total_reserve_value()
        total_supply = self.get_total_supply()
        divisor = 10**decimals

        return {
            "navPerToken": f"{nav_raw / divisor:.{decimals}f}",
            "navPerTokenRaw": nav_raw,
            "totalReserveValue": f"{reserve_raw / divisor:.{decimals}f}",
            "totalReserveValueRaw": reserve_raw,
            "totalSupply": total_supply,
            "totalSupplyFormatted": f"{total_supply / divisor:.{decimals}f}",
            "decimals": decimals,
            "lastNavUpdate": self.get_last_nav_update(),
        }

    @transaction.atomic
    def update_nav(
        self,
        new_nav_per_token: Decimal,
        total_reserve_value: Decimal,
        user,
        yield_token: YieldToken,
        custodian_report_ref: str = "",
        notes: str = "",
        update_on_chain: bool = True,
    ) -> NAVUpdate:
        decimals = yield_token.decimals
        divisor = 10**decimals

        old_nav = yield_token.nav_per_token or Decimal("0")

        nav_update = NAVUpdate.objects.create(
            yield_token=yield_token,
            old_nav_per_token=old_nav,
            new_nav_per_token=new_nav_per_token,
            total_reserve_value=total_reserve_value,
            custodian_report_ref=custodian_report_ref,
            updated_by=user,
            notes=notes,
        )

        if update_on_chain:
            nav_raw = int(new_nav_per_token * divisor)
            reserve_raw = int(total_reserve_value * divisor)

            try:
                contract_function = self.contract.functions.updateNAV(nav_raw, reserve_raw)
                tx_hash, tx_record = self._send_and_confirm(
                    contract_function,
                    tx_type=TransactionType.YIELD_TOKEN_NAV_UPDATE,
                    function_name="updateNAV",
                    function_args={"newNavPerToken": nav_raw, "newReserveValue": reserve_raw},
                    related_model="tokens.NAVUpdate",
                    related_uuid=str(nav_update.uuid),
                )

                nav_update.transaction = tx_record
                nav_update.save(update_fields=["transaction", "updated_at"])

                logger.info(
                    f"{LoggingContext.ASSETS} Updated NAV for {yield_token.symbol}: "
                    f"${old_nav} → ${new_nav_per_token} (tx={tx_hash})"
                )

            except (BaseChainTransactionError, BaseChainContractError) as e:
                logger.error(f"{LoggingContext.ASSETS} On-chain NAV update failed for {yield_token.symbol}: {e}")
                raise YieldTokenNAVUpdateFailedException(f"NAV update failed: {e}") from e

        yield_token.nav_per_token = new_nav_per_token
        yield_token.total_reserve_value = total_reserve_value
        yield_token.last_nav_update = timezone.now()
        yield_token.save(
            update_fields=[
                "nav_per_token",
                "total_reserve_value",
                "last_nav_update",
                "updated_at",
            ]
        )

        try:
            asset = Asset.objects.get(symbol=yield_token.symbol)
            asset.current_price = new_nav_per_token
            asset.price_currency = "USD"
            asset.save(update_fields=["current_price", "price_currency", "updated_at"])

            today_midnight = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            AssetSnapshot.objects.update_or_create(
                asset=asset,
                source_timestamp=today_midnight,
                defaults={
                    "price": new_nav_per_token,
                    "price_currency": "USD",
                    "market_data": {
                        "total_reserve_value": str(total_reserve_value),
                        "custodian_report_ref": custodian_report_ref,
                    },
                    "data_source": "nav_update",
                },
            )
        except Asset.DoesNotExist:
            logger.warning(f"{LoggingContext.ASSETS} Asset record not found for {yield_token.symbol}")

        return nav_update
