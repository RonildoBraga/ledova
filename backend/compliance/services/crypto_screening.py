import logging

from django.conf import settings
from django.utils import timezone

from compliance.constants import (
    ALERT_STATUS_NEW,
    ALERT_TYPE_HIGH_RISK_WALLET,
    ALERT_TYPE_SANCTIONED_ADDRESS,
    SCREENING_RESULT_APPROVED,
    SCREENING_RESULT_REJECTED,
    SCREENING_RESULT_REVIEW,
    SCREENING_STATUS_COMPLETED,
    SCREENING_STATUS_FAILED,
    SCREENING_STATUS_PENDING,
)
from compliance.models import ComplianceAlert, TransactionScreening
from integrations.kyc import get_kyc_provider
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


class CryptoScreeningService:
    def __init__(self):
        self.provider = get_kyc_provider()
        self.provider_name = self.provider.get_provider_name()
        self.enabled = getattr(settings, "KYCAID_CRYPTO_MONITORING_ENABLED", False)
        self.threshold_medium = getattr(settings, "CRYPTO_RISK_THRESHOLD_MEDIUM", 0.25)
        self.threshold_high = getattr(settings, "CRYPTO_RISK_THRESHOLD_HIGH", 0.6)

    def screen_transaction(self, transaction, user_account) -> TransactionScreening:
        if not transaction.to_address:
            logger.warning(f"{LoggingContext.CRYPTO_SCREENING} No destination address for transaction {transaction.pk}")
            return self._create_failed_screening(transaction, user_account, error="No destination address to screen")

        # Return existing screening if one already exists (OneToOne constraint)
        existing = TransactionScreening.objects.filter(transaction=transaction).first()
        if existing:
            return existing

        screening = TransactionScreening.objects.create(
            transaction=transaction,
            user_account=user_account,
            provider=self.provider_name,
            provider_transaction_id=str(transaction.pk),
            to_address=transaction.to_address,
            from_address=getattr(transaction, "from_address", None),
            status=SCREENING_STATUS_PENDING,
        )

        if not self.enabled:
            screening.status = SCREENING_STATUS_FAILED
            screening.error_message = "Crypto monitoring is disabled"
            screening.save()
            logger.warning(
                f"{LoggingContext.CRYPTO_SCREENING} Crypto monitoring disabled for transaction {transaction.pk}"
            )
            return screening

        profile = user_account.user_profiles.first()
        if not profile:
            screening.status = SCREENING_STATUS_FAILED
            screening.error_message = "No user profile found"
            screening.save()
            logger.warning(f"{LoggingContext.CRYPTO_SCREENING} No profile found for user_account {user_account.pk}")
            return screening

        applicant_id = profile.active_applicant_id

        if not applicant_id:
            screening.status = SCREENING_STATUS_FAILED
            screening.error_message = "No applicant ID - user not KYC verified"
            screening.save()
            logger.warning(f"{LoggingContext.CRYPTO_SCREENING} No applicant ID for user_account {user_account.pk}")
            return screening

        try:
            response = self.provider.submit_crypto_transaction(
                applicant_id=applicant_id,
                transaction_id=str(transaction.pk),
                to_address=transaction.to_address,
                from_address=getattr(transaction, "from_address", None),
                amount=str(transaction.amount) if hasattr(transaction, "amount") else None,
                currency=transaction.asset.symbol if hasattr(transaction, "asset") and transaction.asset else None,
                blockchain=self._get_blockchain(transaction),
            )

            self._process_screening_result(screening, response)

            logger.info(
                f"{LoggingContext.CRYPTO_SCREENING} Completed screening for transaction {transaction.pk}: "
                f"result={screening.result}, risk_score={screening.risk_score}"
            )

        except Exception as e:
            screening.status = SCREENING_STATUS_FAILED
            screening.error_message = str(e)
            screening.retry_count += 1
            screening.save()
            logger.error(f"{LoggingContext.CRYPTO_SCREENING} Failed to screen transaction {transaction.pk}: {e}")

        return screening

    def _create_failed_screening(self, transaction, user_account, error: str) -> TransactionScreening:
        return TransactionScreening.objects.create(
            transaction=transaction,
            user_account=user_account,
            provider=self.provider_name,
            provider_transaction_id=str(transaction.pk),
            to_address=transaction.to_address or "",
            from_address=getattr(transaction, "from_address", None),
            status=SCREENING_STATUS_FAILED,
            error_message=error,
        )

    def retry_failed_screening(self, screening: TransactionScreening) -> TransactionScreening:
        if screening.status != SCREENING_STATUS_FAILED:
            logger.warning(
                f"{LoggingContext.CRYPTO_SCREENING} Cannot retry screening {screening.pk} - "
                f"status is {screening.status}"
            )
            return screening

        if not self.enabled:
            logger.warning(
                f"{LoggingContext.CRYPTO_SCREENING} Cannot retry screening {screening.pk} - crypto monitoring disabled"
            )
            return screening

        profile = screening.user_account.user_profiles.first()
        if not profile:
            screening.error_message = "No user profile found"
            screening.retry_count += 1
            screening.save()
            return screening

        applicant_id = profile.active_applicant_id

        if not applicant_id:
            screening.error_message = "No applicant ID - user not KYC verified"
            screening.retry_count += 1
            screening.save()
            return screening

        if not screening.to_address:
            screening.error_message = "No destination address to screen"
            screening.retry_count += 1
            screening.save()
            return screening

        screening.status = SCREENING_STATUS_PENDING
        screening.error_message = None
        screening.save()

        try:
            response = self.provider.submit_crypto_transaction(
                applicant_id=applicant_id,
                transaction_id=screening.provider_transaction_id,
                to_address=screening.to_address,
                from_address=screening.from_address,
                amount=str(screening.transaction.amount) if hasattr(screening.transaction, "amount") else None,
                currency=(
                    screening.transaction.asset.symbol
                    if hasattr(screening.transaction, "asset") and screening.transaction.asset
                    else None
                ),
                blockchain=self._get_blockchain(screening.transaction),
            )

            self._process_screening_result(screening, response)

            logger.info(
                f"{LoggingContext.CRYPTO_SCREENING} Retry succeeded for screening {screening.pk}: "
                f"result={screening.result}, risk_score={screening.risk_score}"
            )

        except Exception as e:
            screening.status = SCREENING_STATUS_FAILED
            screening.error_message = str(e)
            screening.retry_count += 1
            screening.save()
            logger.error(f"{LoggingContext.CRYPTO_SCREENING} Retry failed for screening {screening.pk}: {e}")

        return screening

    def _process_screening_result(self, screening: TransactionScreening, response: dict) -> None:
        screening.raw_response = response
        screening.risk_score = response.get("riskScore", 0)
        screening.risk_signals = response.get("signals", [])
        screening.completed_at = timezone.now()
        screening.status = SCREENING_STATUS_COMPLETED

        if screening.risk_score >= self.threshold_high:
            screening.result = SCREENING_RESULT_REJECTED
            screening.risk_level = "HIGH"
            self._create_alert(screening, severity="high")
        elif screening.risk_score >= self.threshold_medium:
            screening.result = SCREENING_RESULT_REVIEW
            screening.risk_level = "MEDIUM"
            self._create_alert(screening, severity="medium")
        else:
            screening.result = SCREENING_RESULT_APPROVED
            screening.risk_level = "LOW"

        screening.save()

    def _create_alert(self, screening: TransactionScreening, severity: str = "high") -> ComplianceAlert:
        alert_type = self._determine_alert_type(screening.risk_signals)

        alert = ComplianceAlert.objects.create(
            user_account=screening.user_account,
            transaction=screening.transaction,
            alert_type=alert_type,
            severity=severity,
            triggered_rule="CRYPTO-SCREEN",
            description=f"Crypto screening flagged address: {screening.to_address}",
            status=ALERT_STATUS_NEW,
            alert_data={
                "screening_id": str(screening.pk),
                "risk_score": screening.risk_score,
                "risk_signals": screening.risk_signals,
                "to_address": screening.to_address,
                "risk_level": screening.risk_level,
            },
        )

        logger.info(
            f"{LoggingContext.CRYPTO_SCREENING} Created alert {alert.pk} for transaction {screening.transaction_id}: "
            f"type={alert_type}, severity={severity}"
        )

        return alert

    def _determine_alert_type(self, signals: list) -> str:
        sanctions_keywords = ["sanctions", "sanctioned", "ofac", "sdn"]
        for signal in signals:
            signal_lower = str(signal).lower()
            if any(keyword in signal_lower for keyword in sanctions_keywords):
                return ALERT_TYPE_SANCTIONED_ADDRESS

        return ALERT_TYPE_HIGH_RISK_WALLET

    def _get_blockchain(self, transaction) -> str:
        if hasattr(transaction, "wallet") and transaction.wallet:
            wallet = transaction.wallet
            if hasattr(wallet, "blockchain") and wallet.blockchain:
                blockchain = wallet.blockchain.lower()
                if blockchain not in ("hardware", "unknown"):
                    return blockchain
            if hasattr(wallet, "wallet_type"):
                wallet_type = wallet.wallet_type.lower()
                if "bitcoin" in wallet_type or wallet_type == "btc":
                    return "bitcoin"
                if "ethereum" in wallet_type or wallet_type == "eth":
                    return "ethereum"

        # Infer from address format
        if transaction.to_address:
            if transaction.to_address.startswith("0x"):
                return "ethereum"
            if transaction.to_address.startswith(("tb1", "bcrt1", "m", "n", "2")):
                return "bitcoin"

        return "ethereum"

    def process_webhook_result(self, screening: TransactionScreening, data: dict) -> None:
        self._process_screening_result(screening, data)
        logger.info(f"{LoggingContext.CRYPTO_SCREENING} Processed webhook result for screening {screening.pk}")
