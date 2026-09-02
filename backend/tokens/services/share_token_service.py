import logging
from typing import Optional

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from web3 import Web3

from integrations.base_chain import get_base_chain_client
from integrations.base_chain.exceptions import (
    BaseChainContractError,
    BaseChainTransactionError,
)
from shared.utils.logging_utils import LoggingContext
from tokens.exceptions import (
    ContractLoadException,
    InvalidHolderAddressException,
    InvalidRecipientAddressException,
    InvalidTokenAddressException,
    InvalidTokenStateException,
    OperatorKeyNotConfiguredException,
    ShareIssuanceFailedException,
    TokenBalanceRetrievalException,
    TokenDeploymentFailedException,
    TokenFactoryNotConfiguredException,
)
from tokens.models import ShareIssuance, ShareIssuanceRequest, ShareToken, Stablecoin

logger = logging.getLogger(__name__)


class ShareTokenService:
    def __init__(self):
        self.chain_client = get_base_chain_client()
        self._factory_contract = None

    # --- Configuration ---

    @property
    def factory_address(self) -> str:
        address = getattr(settings, "SHARE_TOKEN_FACTORY_ADDRESS", "")
        if not address:
            raise TokenFactoryNotConfiguredException(
                "SHARE_TOKEN_FACTORY_ADDRESS not configured. "
                "Please deploy the ShareTokenFactory contract and set the address."
            )
        return address

    @property
    def signer_key(self) -> str:
        key = getattr(settings, "BLOCKCHAIN_OPERATOR_KEY", "")
        if not key:
            raise OperatorKeyNotConfiguredException()
        return key

    @property
    def factory_contract(self):
        if self._factory_contract is None:
            try:
                self._factory_contract = self.chain_client.load_contract(
                    "ShareTokenFactory",
                    self.factory_address,
                )
            except BaseChainContractError as e:
                raise ContractLoadException(f"Failed to load contract: {e}") from e
        return self._factory_contract

    # --- Helpers ---

    def _validate_address(self, address: str) -> str:
        """Validate an Ethereum address and return its checksum form."""
        if not self.chain_client.is_valid_address(address):
            raise InvalidRecipientAddressException()
        return self.chain_client.to_checksum_address(address)

    @staticmethod
    def _tx_result(tx_hash: str, receipt: dict | None) -> dict:
        """Extract standard transaction result from a receipt."""
        return {
            "tx_hash": tx_hash,
            "block_number": receipt["blockNumber"] if receipt else None,
            "gas_used": receipt["gasUsed"] if receipt else None,
        }

    def _mint_to(self, contract_address: str, recipient: str, amount: int) -> dict:
        """
        Execute an on-chain mint call. Shared by initial supply and additional issuances.

        Returns:
            dict with tx_hash, block_number, gas_used
        """
        token_contract = self.load_share_token(contract_address)
        recipient_checksum = self.chain_client.to_checksum_address(recipient)

        mint_fn = token_contract.functions.mint(recipient_checksum, amount)
        tx_hash, receipt = self.chain_client.send_transaction(
            mint_fn,
            self.signer_key,
            wait_for_receipt=True,
        )

        return self._tx_result(tx_hash, receipt)

    def _get_balance(self, contract_name: str, contract_address: str, holder: str) -> int:
        """Get token balance for a holder. Works with any ERC20-compatible contract."""
        if not self.chain_client.is_valid_address(holder):
            raise InvalidHolderAddressException()

        contract = self.chain_client.load_contract(
            contract_name, self.chain_client.to_checksum_address(contract_address)
        )
        holder_checksum = self.chain_client.to_checksum_address(holder)

        return contract.functions.balanceOf(holder_checksum).call()

    # --- Contract loading ---

    def load_share_token(self, contract_address: str):
        if not self.chain_client.is_valid_address(contract_address):
            raise InvalidTokenAddressException()

        checksum = self.chain_client.to_checksum_address(contract_address)
        return self.chain_client.load_contract("ShareToken", checksum)

    # --- Deployment ---

    def deploy_share_token(
        self,
        name: str,
        symbol: str,
        identifier: str,
        authorized_shares: int,
        company_wallet_address: str,
    ) -> dict:
        try:
            company_checksum = self._validate_address(company_wallet_address)
            signer_address = self.chain_client.get_address_from_private_key(self.signer_key)

            logger.info(
                f"{LoggingContext.TOKEN} Deploying ShareToken: {name} ({symbol}) "
                f"with {authorized_shares} shares for company wallet: {company_checksum}"
            )

            create_fn = self.factory_contract.functions.createShareToken(
                name,
                symbol,
                identifier,
                authorized_shares,
                signer_address,
            )

            tx_hash, receipt = self.chain_client.send_transaction(
                create_fn,
                self.signer_key,
                wait_for_receipt=True,
            )

            result = {"deploy_tx_hash": tx_hash, "contract_address": None, "mint_result": None}

            if receipt:
                token_created_events = self.factory_contract.events.ShareTokenCreated().process_receipt(receipt)
                if token_created_events:
                    contract_address = token_created_events[0]["args"]["tokenAddress"]
                    logger.info(f"{LoggingContext.TOKEN} ShareToken deployed at: {contract_address}")

                    result["contract_address"] = contract_address
                    result["mint_result"] = self._mint_to(contract_address, company_checksum, authorized_shares)

            return result

        except BaseChainTransactionError as e:
            logger.error(f"{LoggingContext.TOKEN} Transaction failed: {e}")
            raise TokenDeploymentFailedException(f"Token deployment failed: {e}") from e
        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN} Deployment error: {e}")
            raise TokenDeploymentFailedException(f"Token deployment failed: {e}") from e

    # --- Issuance ---

    def create_issuance_request(
        self, token, recipient: str, amount: int, user, reason: str = "", issuance_type: str = "additional"
    ) -> ShareIssuanceRequest:
        """
        Validate inputs and create a ShareIssuanceRequest record for approval.

        Raises:
            InvalidTokenStateException: If token is not deployed
            InvalidRecipientAddressException: If recipient address is invalid
            ValidationError: If amount is invalid
        """
        if token.status != "deployed":
            raise InvalidTokenStateException("Only deployed tokens can issue shares.")

        if not token.contract_address:
            raise InvalidTokenStateException("Token has no contract address.")

        if not recipient or not Web3.is_address(recipient):
            raise InvalidRecipientAddressException()

        if amount <= 0:
            raise ValidationError({"amount": "Amount must be a positive integer."})

        issuance_request = ShareIssuanceRequest.objects.create(
            token=token,
            recipient_address=recipient,
            amount=amount,
            issuance_type=issuance_type,
            reason=reason,
            submitted_by=user,
            submitted_at=timezone.now(),
        )

        # Calculate dilution after creation
        issuance_request.dilution_percentage = issuance_request.calculate_dilution()
        issuance_request.save(update_fields=["dilution_percentage", "updated_at"])

        logger.info(
            f"{LoggingContext.TOKEN} User {user.email} created issuance request: "
            f"{amount} {token.symbol} to {recipient}"
        )

        return issuance_request

    def mint_shares(self, issuance: ShareIssuance) -> dict:
        """
        Execute on-chain mint for a pending ShareIssuance.

        Raises:
            ShareIssuanceFailedException: If minting fails
        """
        token = issuance.token

        if not token.contract_address or token.status != "deployed":
            error = "Token is not deployed on blockchain"
            issuance.mark_failed(error)
            raise ShareIssuanceFailedException(f"Share issuance failed: {error}")

        issuance.mark_processing()

        try:
            logger.info(
                f"{LoggingContext.TOKEN} Minting {issuance.amount} {token.symbol} to {issuance.recipient_address}"
            )

            result = self._mint_to(token.contract_address, issuance.recipient_address, int(issuance.amount))

            issuance.mark_completed(
                tx_hash=result["tx_hash"],
                block_number=result["block_number"],
                gas_used=result["gas_used"],
            )

            logger.info(
                f"{LoggingContext.TOKEN} Issuance complete: {issuance.amount} {token.symbol} - tx: {result['tx_hash']}"
            )

            return result

        except Exception as e:
            issuance.mark_failed(str(e))
            logger.error(f"{LoggingContext.TOKEN} Issuance mint failed: {e}")
            raise ShareIssuanceFailedException(f"Share issuance failed: {e}") from e

    # --- Capital increases ---

    def increase_authorized_shares(
        self,
        contract_address: str,
        additional_shares: int,
        company_wallet: str,
    ) -> dict:
        try:
            company_checksum = self._validate_address(company_wallet)
            token_contract = self.load_share_token(contract_address)

            current_authorized = token_contract.functions.authorizedShares().call()
            new_authorized = current_authorized + additional_shares

            logger.info(
                f"{LoggingContext.TOKEN} Increasing authorized shares: "
                f"{current_authorized} -> {new_authorized} (+{additional_shares})"
            )

            set_auth_fn = token_contract.functions.setAuthorizedShares(new_authorized)
            set_auth_tx_hash, _ = self.chain_client.send_transaction(
                set_auth_fn,
                self.signer_key,
                wait_for_receipt=True,
            )

            logger.info(f"{LoggingContext.TOKEN} Authorized shares increased - tx: {set_auth_tx_hash}")

            mint_result = self._mint_to(contract_address, company_checksum, additional_shares)

            logger.info(
                f"{LoggingContext.TOKEN} Minted {additional_shares} shares "
                f"to {company_checksum} - tx: {mint_result['tx_hash']}"
            )

            return {
                "set_authorized_tx_hash": set_auth_tx_hash,
                "mint_tx_hash": mint_result["tx_hash"],
                "new_authorized_total": new_authorized,
                "block_number": mint_result["block_number"],
                "gas_used": mint_result["gas_used"],
            }

        except BaseChainTransactionError as e:
            logger.error(f"{LoggingContext.TOKEN} Capital increase transaction failed: {e}")
            raise TokenDeploymentFailedException(f"Token deployment failed: {e}") from e
        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN} Capital increase error: {e}")
            raise TokenDeploymentFailedException(f"Token deployment failed: {e}") from e

    # --- Queries ---

    def get_token_balance(self, contract_address: str, holder: str) -> int:
        try:
            return self._get_balance("ShareToken", contract_address, holder)
        except InvalidHolderAddressException:
            raise
        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN} Error getting balance: {e}")
            raise TokenBalanceRetrievalException() from e

    def get_token_by_identifier(self, identifier: str) -> Optional[str]:
        try:
            address = self.factory_contract.functions.getTokenByIdentifier(identifier).call()
            if address == "0x0000000000000000000000000000000000000000":
                return None
            return address
        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN} Error getting token by identifier: {e}")
            return None

    # --- Holders ---

    def get_token_holders(self, token) -> list[dict]:
        holders_data = []

        if token.status == "deployed" and token.contract_address:
            try:
                issuances_qs = ShareIssuance.objects.filter_by_token(token)
                address_names = issuances_qs.unique_holders_with_names()

                for address in address_names.keys():
                    try:
                        balance = self.get_token_balance(token.contract_address, address)
                        if balance > 0:
                            holders_data.append(
                                {
                                    "address": address,
                                    "name": address_names.get(address) or None,
                                    "balance": str(balance),
                                    "source": "blockchain",
                                }
                            )
                    except Exception as e:
                        logger.warning(f"{LoggingContext.TOKEN} Failed to get balance for {address}: {e}")

            except Exception as e:
                logger.error(f"{LoggingContext.TOKEN} Failed to query blockchain for holders: {e}")
                holders_data = ShareIssuance.objects.filter_by_token(token).holders_as_list()
        else:
            holders_data = ShareIssuance.objects.filter_by_token(token).holders_as_list()

        total_supply = sum(int(h["balance"]) for h in holders_data) if holders_data else 0
        for holder in holders_data:
            balance = int(holder["balance"])
            holder["percentage"] = round((balance / total_supply * 100), 2) if total_supply > 0 else 0

        holders_data.sort(key=lambda x: int(x["balance"]), reverse=True)

        return holders_data

    # --- Wallet balances ---

    def get_wallet_token_balances(self, wallet_address: str) -> dict:
        wallet_checksum = self._validate_address(wallet_address)

        balances = []

        tokens = ShareToken.objects.deployed_with_contract()
        for token in tokens:
            try:
                balance = self.get_token_balance(token.contract_address, wallet_checksum)
                if balance > 0:
                    balances.append(
                        {
                            "token": str(token.uuid),
                            "symbol": token.symbol,
                            "name": token.name,
                            "balance": str(balance),
                            "contractAddress": token.contract_address,
                            "decimals": 0,
                            "type": "share_token",
                        }
                    )
            except Exception as e:
                logger.warning(f"{LoggingContext.TOKEN} Failed to get balance for {token.symbol}: {e}")

        stablecoins = (
            Stablecoin.objects.filter(is_active=True)
            .exclude(contract_address__isnull=True)
            .exclude(contract_address="")
        )
        for stablecoin in stablecoins:
            try:
                balance = self._get_balance("AUDY", stablecoin.contract_address, wallet_checksum)
                if balance > 0:
                    balances.append(
                        {
                            "token": str(stablecoin.uuid),
                            "symbol": stablecoin.symbol,
                            "name": stablecoin.name,
                            "balance": str(balance),
                            "contractAddress": stablecoin.contract_address,
                            "decimals": stablecoin.decimals,
                            "type": "stablecoin",
                        }
                    )
            except Exception as e:
                logger.warning(f"{LoggingContext.TOKEN} Failed to get stablecoin balance for {stablecoin.symbol}: {e}")

        return {"walletAddress": wallet_checksum, "balances": balances}
