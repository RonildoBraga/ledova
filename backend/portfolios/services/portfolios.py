import logging

from portfolios.exceptions import (
    InactivePortfolioException,
    WalletAlreadyInPortfolioException,
    WalletNotFoundException,
    WalletNotInPortfolioException,
    WalletOwnershipException,
)
from portfolios.models.portfolio import Portfolio
from shared.utils.logging_utils import LoggingContext
from wallets.models import Wallet

logger = logging.getLogger("ledova_backend")


class PortfolioWalletService:
    @staticmethod
    def add_wallet_to_portfolio(portfolio: Portfolio, wallet_uuid: str) -> Portfolio:
        if not portfolio.is_active:
            raise InactivePortfolioException(portfolio.uuid)

        try:
            wallet = Wallet.objects.get(uuid=wallet_uuid)
        except Wallet.DoesNotExist:
            raise WalletNotFoundException(wallet_uuid)

        if wallet.user_account != portfolio.user_account:
            logger.warning(
                f"{LoggingContext.PORTFOLIOS} Attempted to add wallet {wallet_uuid} "
                f"to portfolio {portfolio.uuid} - ownership mismatch"
            )
            raise WalletOwnershipException()

        if portfolio.wallets.filter(uuid=wallet.uuid).exists():
            raise WalletAlreadyInPortfolioException()

        portfolio.wallets.add(wallet)

        logger.info(f"{LoggingContext.PORTFOLIOS} Added wallet {wallet.address[:10]}... to portfolio {portfolio.uuid}")

        portfolio.refresh_from_db()
        return portfolio

    @staticmethod
    def remove_wallet_from_portfolio(portfolio: Portfolio, wallet_uuid: str) -> Portfolio:
        if not portfolio.is_active:
            raise InactivePortfolioException(portfolio.uuid)

        try:
            wallet = Wallet.objects.get(uuid=wallet_uuid)
        except Wallet.DoesNotExist:
            raise WalletNotFoundException(wallet_uuid)

        if not portfolio.wallets.filter(uuid=wallet.uuid).exists():
            raise WalletNotInPortfolioException()

        portfolio.wallets.remove(wallet)

        logger.info(
            f"{LoggingContext.PORTFOLIOS} Removed wallet {wallet.address[:10]}... from portfolio {portfolio.uuid}"
        )

        portfolio.refresh_from_db()
        return portfolio
