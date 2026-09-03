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

SANCTIONS_KEYWORDS = ("sanctions", "sanctioned", "ofac", "sdn")


class CryptoScreeningService:
    def __init__(self):
        self.provider = get_kyc_provider()
        self.provider_name = self.provider.get_provider_name()
        self.enabled = getattr(settings, "KYCAID_CRYPTO_MONITORING_ENABLED", False)
        self.threshold_medium = getattr(settings, "CRYPTO_RISK_THRESHOLD_MEDIUM", 0.25)
        self.threshold_high = getattr(settings, "CRYPTO_RISK_THRESHOLD_HIGH", 0.6)

    def screen_transaction(self, transaction, user_account) -> TransactionScreening:
        existing = TransactionScreening.objects.filter(transaction=transaction).first()
        if existing:
            return existing
        screening = TransactionScreening.objects.create(
            transaction=transaction,
            user_account=user_account,
            provider=self.provider_name,
            provider_transaction_id=str(transaction.pk),
            to_address=transaction.to_address or "",
            from_address=transaction.from_address,
            status=SCREENING_STATUS_PENDING,
        )
        blocker = self._blocker(screening)
        if blocker:
            screening.status = SCREENING_STATUS_FAILED
            screening.error_message = blocker
            screening.save()
            logger.warning(f"{LoggingContext.CRYPTO_SCREENING} Transaction {transaction.pk} not screened: {blocker}")
            return screening
        return self._submit(screening)

    def retry_failed_screening(self, screening: TransactionScreening) -> TransactionScreening:
        if screening.status != SCREENING_STATUS_FAILED or not self.enabled:
            logger.warning(f"{LoggingContext.CRYPTO_SCREENING} Cannot retry screening {screening.pk}")
            return screening
        blocker = self._blocker(screening)
        if blocker:
            screening.error_message = blocker
            screening.retry_count += 1
            screening.save()
            return screening
        screening.status = SCREENING_STATUS_PENDING
        screening.error_message = None
        screening.save()
        return self._submit(screening)

    def process_webhook_result(self, screening: TransactionScreening, data: dict) -> None:
        self._process_screening_result(screening, data)
        logger.info(f"{LoggingContext.CRYPTO_SCREENING} Processed webhook result for screening {screening.pk}")

    def _blocker(self, screening) -> str:
        """The reason the screening cannot be submitted to the provider, or '' when it can."""
        if not screening.to_address:
            return "No destination address to screen"
        if not self.enabled:
            return "Crypto monitoring is disabled"
        profile = screening.user_account.user_profiles.first()
        if not profile:
            return "No user profile found"
        if not profile.active_applicant_id:
            return "No applicant ID - user not KYC verified"
        return ""

    def _submit(self, screening) -> TransactionScreening:
        transaction = screening.transaction
        try:
            response = self.provider.submit_crypto_transaction(
                applicant_id=screening.user_account.user_profiles.first().active_applicant_id,
                transaction_id=screening.provider_transaction_id,
                to_address=screening.to_address,
                from_address=screening.from_address,
                amount=str(transaction.amount),
                currency=transaction.asset.symbol if transaction.asset_id else None,
                blockchain=self._get_blockchain(transaction),
            )
            self._process_screening_result(screening, response)
            logger.info(
                f"{LoggingContext.CRYPTO_SCREENING} Screened transaction {transaction.pk}: "
                f"result={screening.result}, risk_score={screening.risk_score}"
            )
        except Exception as e:
            screening.status = SCREENING_STATUS_FAILED
            screening.error_message = str(e)
            screening.retry_count += 1
            screening.save()
            logger.error(f"{LoggingContext.CRYPTO_SCREENING} Failed to screen transaction {transaction.pk}: {e}")
        return screening

    def _process_screening_result(self, screening: TransactionScreening, response: dict) -> None:
        screening.raw_response = response
        screening.risk_score = response.get("riskScore", 0)
        screening.risk_signals = response.get("signals", [])
        screening.completed_at = timezone.now()
        screening.status = SCREENING_STATUS_COMPLETED
        if screening.risk_score >= self.threshold_high:
            screening.result, screening.risk_level = SCREENING_RESULT_REJECTED, "HIGH"
            self._create_alert(screening, severity="high")
        elif screening.risk_score >= self.threshold_medium:
            screening.result, screening.risk_level = SCREENING_RESULT_REVIEW, "MEDIUM"
            self._create_alert(screening, severity="medium")
        else:
            screening.result, screening.risk_level = SCREENING_RESULT_APPROVED, "LOW"
        screening.save()

    def _create_alert(self, screening: TransactionScreening, severity: str) -> ComplianceAlert:
        sanctioned = any(
            keyword in str(signal).lower() for signal in screening.risk_signals for keyword in SANCTIONS_KEYWORDS
        )
        alert = ComplianceAlert.objects.create(
            user_account=screening.user_account,
            transaction=screening.transaction,
            alert_type=ALERT_TYPE_SANCTIONED_ADDRESS if sanctioned else ALERT_TYPE_HIGH_RISK_WALLET,
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
            f"type={alert.alert_type}, severity={severity}"
        )
        return alert

    @staticmethod
    def _get_blockchain(transaction) -> str:
        """Provider-facing chain name: the wallet's chain, else inferred from the address format."""
        chain = (transaction.wallet.chain or "").lower() if transaction.wallet_id else ""
        if chain and chain not in ("hardware", "unknown"):
            return chain
        if transaction.to_address and transaction.to_address.startswith(("tb1", "bcrt1", "m", "n", "2")):
            return "bitcoin"
        return "ethereum"
