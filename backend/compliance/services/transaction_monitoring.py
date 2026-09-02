import logging
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Tuple

from django.db.models import Avg, Sum
from django.utils import timezone

from compliance.constants import (
    AGGREGATE_VOLUME_PERIOD_DAYS,
    AGGREGATE_VOLUME_THRESHOLD_AUD,
    ALERT_STATUS_NEW,
    ALERT_STATUS_REVIEWING,
    ALERT_THRESHOLD_AUD,
    ALERT_TYPE_DORMANT_REACTIVATION,
    ALERT_TYPE_EXTREME_RISK_TRANSACTION,
    ALERT_TYPE_HIGH_AGGREGATE_VOLUME,
    ALERT_TYPE_HIGH_RISK_WALLET,
    ALERT_TYPE_LARGE_TRANSACTION,
    ALERT_TYPE_NEW_CUSTOMER_SOF,
    ALERT_TYPE_PATTERN_DEVIATION,
    ALERT_TYPE_RAPID_TRANSACTIONS,
    ALERT_TYPE_ROUND_AMOUNTS,
    ALERT_TYPE_SANCTIONED_ADDRESS,
    ALERT_TYPE_STRUCTURING,
    DORMANT_ACCOUNT_DAYS,
    HIGH_RISK_RATINGS,
    PATTERN_DEVIATION_BASELINE_DAYS,
    PATTERN_DEVIATION_MIN_HISTORY,
    PATTERN_DEVIATION_MULTIPLIER,
    RISK_RATING_EXTREME,
    ROUND_AMOUNT_COUNT_THRESHOLD,
    ROUND_AMOUNT_DIVISOR,
    ROUND_AMOUNT_PERIOD_DAYS,
    RULE_TYPE_ADDRESS,
    RULE_TYPE_AGGREGATE_VOLUME,
    RULE_TYPE_DORMANT_REACTIVATION,
    RULE_TYPE_EXTREME_RISK,
    RULE_TYPE_PATTERN,
    RULE_TYPE_PATTERN_DEVIATION,
    RULE_TYPE_RAPID_TRANSACTIONS,
    RULE_TYPE_ROUND_AMOUNTS,
    RULE_TYPE_SOF_REQUIRED,
    RULE_TYPE_THRESHOLD,
    SCREENING_THRESHOLD_AUD,
    TRANSACTION_MONITORING_WINDOW_HOURS,
)
from compliance.models import ComplianceAlert, MonitoringRule
from compliance.services.tier_progression import TierProgressionService
from shared.utils.logging_utils import LoggingContext
from wallets.models import Transaction

logger = logging.getLogger("ledova_backend")

RULE_CODE_TO_ALERT_TYPE = {
    "MON-001": ALERT_TYPE_LARGE_TRANSACTION,
    "MON-002": ALERT_TYPE_RAPID_TRANSACTIONS,
    "MON-003": ALERT_TYPE_STRUCTURING,
    "MON-004": ALERT_TYPE_HIGH_RISK_WALLET,
    "MON-005": ALERT_TYPE_SANCTIONED_ADDRESS,
    "MON-006": ALERT_TYPE_NEW_CUSTOMER_SOF,
    "MON-007": ALERT_TYPE_HIGH_AGGREGATE_VOLUME,
    "MON-008": ALERT_TYPE_DORMANT_REACTIVATION,
    "MON-009": ALERT_TYPE_PATTERN_DEVIATION,
    "MON-010": ALERT_TYPE_ROUND_AMOUNTS,
    "MON-011": ALERT_TYPE_EXTREME_RISK_TRANSACTION,
}


class TransactionMonitoringService:
    @classmethod
    def check_new_transaction(cls, tx) -> None:
        """Screen a just-created wallet transaction. Never raises: a monitoring
        failure must not roll back the sync or transfer that created the row."""
        cutoff = timezone.now() - timedelta(hours=TRANSACTION_MONITORING_WINDOW_HOURS)
        if tx.block_timestamp and tx.block_timestamp < cutoff:
            return
        try:
            alerts = cls.check_transaction(transaction=tx, user_account=tx.wallet.user_account)
            if alerts:
                logger.info(f"{LoggingContext.MONITORING} Created {len(alerts)} alert(s) for transaction {tx.uuid}")
        except Exception:
            logger.exception(f"{LoggingContext.MONITORING} Error checking transaction {tx.uuid}")

    @classmethod
    def check_transaction(cls, transaction, user_account) -> List[ComplianceAlert]:
        alerts_created = []
        active_rules = MonitoringRule.objects.active()

        for rule in active_rules:
            triggered, details = cls._check_rule(rule, transaction, user_account)

            if triggered:
                alert = cls._create_alert(
                    rule=rule,
                    user_account=user_account,
                    transaction=transaction,
                    details=details,
                )
                alerts_created.append(alert)
                logger.info(
                    f"{LoggingContext.MONITORING} Rule {rule.rule_code} triggered for "
                    f"user_account {user_account.uuid}, transaction {transaction.uuid}"
                )

        return alerts_created

    @classmethod
    def _check_rule(cls, rule: MonitoringRule, transaction, user_account) -> Tuple[bool, Dict]:
        rule_type = rule.rule_type

        if rule_type == RULE_TYPE_THRESHOLD:
            return cls._check_threshold_rule(rule, transaction)
        elif rule_type == RULE_TYPE_RAPID_TRANSACTIONS:
            return cls._check_rapid_transactions_rule(rule, user_account)
        elif rule_type == RULE_TYPE_PATTERN:
            return cls._check_pattern_rule(rule, user_account)
        elif rule_type == RULE_TYPE_ADDRESS:
            return cls._check_address_rule(rule, transaction, user_account)
        elif rule_type == RULE_TYPE_SOF_REQUIRED:
            return cls._check_sof_required_rule(rule, transaction, user_account)
        elif rule_type == RULE_TYPE_AGGREGATE_VOLUME:
            return cls._check_aggregate_volume_rule(rule, user_account)
        elif rule_type == RULE_TYPE_DORMANT_REACTIVATION:
            return cls._check_dormant_reactivation_rule(rule, transaction, user_account)
        elif rule_type == RULE_TYPE_PATTERN_DEVIATION:
            return cls._check_pattern_deviation_rule(rule, transaction, user_account)
        elif rule_type == RULE_TYPE_ROUND_AMOUNTS:
            return cls._check_round_amounts_rule(rule, user_account)
        elif rule_type == RULE_TYPE_EXTREME_RISK:
            return cls._check_extreme_risk_rule(rule, transaction, user_account)

        return False, {}

    @classmethod
    def _check_threshold_rule(cls, rule: MonitoringRule, transaction) -> Tuple[bool, Dict]:
        params = rule.parameters
        threshold = Decimal(str(params.get("amount", ALERT_THRESHOLD_AUD)))
        amount = transaction.market_value or Decimal("0")

        if amount >= threshold:
            return True, {
                "amount": float(amount),
                "threshold": float(threshold),
                "currency": params.get("currency", "AUD"),
            }
        return False, {}

    @classmethod
    def _check_rapid_transactions_rule(cls, rule: MonitoringRule, user_account) -> Tuple[bool, Dict]:
        from wallets.models import Transaction

        params = rule.parameters
        max_transactions = params.get("max_transactions", 5)
        period_minutes = params.get("period_minutes", 60)

        period_start = timezone.now() - timedelta(minutes=period_minutes)
        transaction_count = Transaction.objects.filter(
            wallet__user_account=user_account,
            created_at__gte=period_start,
        ).count()

        if transaction_count >= max_transactions:
            return True, {
                "transaction_count": transaction_count,
                "threshold": max_transactions,
                "period_minutes": period_minutes,
                "reason": f"{transaction_count} transactions in {period_minutes} minutes",
            }
        return False, {}

    @classmethod
    def _check_pattern_rule(cls, rule: MonitoringRule, user_account) -> Tuple[bool, Dict]:
        from wallets.models import Transaction

        params = rule.parameters
        min_transactions = params.get("min_transactions", 3)
        max_each = Decimal(str(params.get("max_each", 9999)))
        min_each = Decimal(str(params.get("min_each", 8000)))
        period_hours = params.get("period_hours", 168)

        period_start = timezone.now() - timedelta(hours=period_hours)
        suspicious_txns = Transaction.objects.filter(
            wallet__user_account=user_account,
            created_at__gte=period_start,
            market_value__gte=min_each,
            market_value__lte=max_each,
        ).count()

        if suspicious_txns >= min_transactions:
            return True, {
                "transaction_count": suspicious_txns,
                "min_required": min_transactions,
                "amount_range": f"${float(min_each):,.0f} - ${float(max_each):,.0f}",
                "period_hours": period_hours,
                "pattern": "potential_structuring",
            }
        return False, {}

    @classmethod
    def _should_screen_address(cls, transaction, user_account) -> Tuple[bool, str]:
        from compliance.models import CustomerRiskAssessment

        latest_assessment = CustomerRiskAssessment.objects.filter(
            user_account=user_account,
            assessment_status="complete",
        ).first()

        if latest_assessment and latest_assessment.overall_risk_rating in HIGH_RISK_RATINGS:
            return True, "high_risk_customer"

        amount = transaction.market_value or Decimal("0")
        if amount >= SCREENING_THRESHOLD_AUD:
            return True, "large_transaction"

        if TierProgressionService.is_new_customer(user_account):
            return True, "new_customer"

        return False, "not_required"

    @classmethod
    def _check_address_rule(cls, _rule: MonitoringRule, transaction, user_account) -> Tuple[bool, Dict]:
        from compliance.constants import (
            SCREENING_RESULT_REJECTED,
            SCREENING_RESULT_REVIEW,
            SCREENING_STATUS_FAILED,
        )
        from compliance.services.crypto_screening import CryptoScreeningService

        should_screen, reason = cls._should_screen_address(transaction, user_account)

        if not should_screen:
            logger.debug(
                f"{LoggingContext.MONITORING} Skipping address screening for transaction {transaction.uuid} "
                f"(reason: {reason})"
            )
            return False, {}

        logger.info(
            f"{LoggingContext.MONITORING} Address screening triggered for transaction {transaction.uuid} "
            f"(reason: {reason})"
        )

        screening_service = CryptoScreeningService()
        screening = screening_service.screen_transaction(transaction, user_account)

        if screening.status == SCREENING_STATUS_FAILED:
            return True, {
                "flagged_address": screening.to_address,
                "screening_id": str(screening.pk),
                "error": screening.error_message,
                "screening_trigger": reason,
                "reason": "Crypto screening failed - address safety unverified",
            }
        elif screening.result == SCREENING_RESULT_REJECTED:
            return True, {
                "flagged_address": screening.to_address,
                "risk_score": screening.risk_score,
                "risk_signals": screening.risk_signals,
                "screening_id": str(screening.pk),
                "screening_trigger": reason,
                "reason": "Crypto screening flagged high-risk address",
            }
        elif screening.result == SCREENING_RESULT_REVIEW:
            return True, {
                "flagged_address": screening.to_address,
                "risk_score": screening.risk_score,
                "risk_signals": screening.risk_signals,
                "screening_id": str(screening.pk),
                "screening_trigger": reason,
                "reason": "Crypto screening requires manual review",
            }

        return False, {}

    @classmethod
    def _check_sof_required_rule(cls, rule: MonitoringRule, transaction, user_account) -> Tuple[bool, Dict]:
        if transaction is None:
            return False, {}

        params = rule.parameters
        threshold = Decimal(str(params.get("amount", ALERT_THRESHOLD_AUD)))
        customer_age_days = params.get("customer_age_days", 30)

        if not TierProgressionService.is_new_customer(user_account, days=customer_age_days):
            return False, {}

        amount = transaction.market_value or Decimal("0")
        if amount < threshold:
            return False, {}

        has_sof = cls._has_sof_documentation(user_account)

        if not has_sof:
            return True, {
                "amount": float(amount),
                "threshold": float(threshold),
                "has_sof_documentation": False,
                "customer_age_days": customer_age_days,
                "reason": "High-value transaction by new customer without SOF documentation",
                "action_required": "Request source of funds documentation",
            }
        return False, {}

    @classmethod
    def _has_sof_documentation(cls, user_account) -> bool:
        director = user_account.director
        if not director:
            director = user_account.user_profiles.first()

        if director:
            financial_profile = getattr(director, "financial_profile", None)
            if financial_profile:
                sof = financial_profile.source_of_funds
                if sof and sof != "other" and sof != ["other"]:
                    return True
        return False

    @classmethod
    def _check_aggregate_volume_rule(cls, rule: MonitoringRule, user_account) -> Tuple[bool, Dict]:
        from wallets.models import FiatTransaction, Transaction

        params = rule.parameters
        threshold = Decimal(str(params.get("amount", AGGREGATE_VOLUME_THRESHOLD_AUD)))
        period_days = params.get("period_days", AGGREGATE_VOLUME_PERIOD_DAYS)

        period_start = timezone.now() - timedelta(days=period_days)

        crypto_volume = Transaction.objects.filter(
            wallet__user_account=user_account,
            created_at__gte=period_start,
            market_value__isnull=False,
        ).aggregate(total=Sum("market_value"))["total"] or Decimal("0")

        fiat_volume = FiatTransaction.objects.filter(
            user__userprofile__user_accounts=user_account,
            created_at__gte=period_start,
            fiat_amount__isnull=False,
        ).aggregate(total=Sum("fiat_amount"))["total"] or Decimal("0")

        total_volume = crypto_volume + fiat_volume

        if total_volume >= threshold:
            return True, {
                "total_volume": float(total_volume),
                "crypto_volume": float(crypto_volume),
                "fiat_volume": float(fiat_volume),
                "threshold": float(threshold),
                "period_days": period_days,
                "reason": f"High aggregate volume: ${float(total_volume):,.2f} in {period_days} days",
            }
        return False, {}

    @classmethod
    def _check_dormant_reactivation_rule(cls, rule: MonitoringRule, transaction, user_account) -> Tuple[bool, Dict]:
        from wallets.models import Transaction

        if transaction is None:
            return False, {}

        params = rule.parameters
        dormant_days = params.get("dormant_days", DORMANT_ACCOUNT_DAYS)
        min_amount = Decimal(str(params.get("min_amount", SCREENING_THRESHOLD_AUD)))

        current_amount = transaction.market_value or Decimal("0")
        if current_amount < min_amount:
            return False, {}

        previous_transaction = (
            Transaction.objects.filter(
                wallet__user_account=user_account,
                created_at__lt=transaction.created_at,
            )
            .order_by("-created_at")
            .first()
        )

        if not previous_transaction:
            return False, {}

        days_inactive = (transaction.created_at - previous_transaction.created_at).days

        if days_inactive >= dormant_days:
            return True, {
                "days_inactive": days_inactive,
                "dormant_threshold": dormant_days,
                "transaction_amount": float(current_amount),
                "min_amount": float(min_amount),
                "last_activity": previous_transaction.created_at.isoformat(),
                "reason": (
                    f"Dormant account reactivation after {days_inactive} days "
                    f"with ${float(current_amount):,.2f} transaction"
                ),
            }
        return False, {}

    @classmethod
    def _check_pattern_deviation_rule(cls, rule: MonitoringRule, transaction, user_account) -> Tuple[bool, Dict]:
        if transaction is None:
            return False, {}

        params = rule.parameters
        multiplier = params.get("multiplier", PATTERN_DEVIATION_MULTIPLIER)
        min_history = params.get("min_history", PATTERN_DEVIATION_MIN_HISTORY)
        baseline_days = params.get("baseline_days", PATTERN_DEVIATION_BASELINE_DAYS)

        current_amount = transaction.market_value or Decimal("0")
        if current_amount <= Decimal("0"):
            return False, {}

        baseline_start = timezone.now() - timedelta(days=baseline_days)

        historical_txns = Transaction.objects.filter(
            wallet__user_account=user_account,
            created_at__gte=baseline_start,
            market_value__isnull=False,
            market_value__gt=0,
        ).exclude(uuid=transaction.uuid)

        txn_count = historical_txns.count()
        if txn_count < min_history:
            return False, {}

        avg_result = historical_txns.aggregate(avg=Avg("market_value"))
        avg_amount = avg_result["avg"] or Decimal("0")

        if avg_amount <= Decimal("0"):
            return False, {}

        deviation_threshold = avg_amount * multiplier

        if current_amount >= deviation_threshold:
            return True, {
                "transaction_amount": float(current_amount),
                "average_amount": float(avg_amount),
                "deviation_multiplier": multiplier,
                "deviation_threshold": float(deviation_threshold),
                "historical_count": txn_count,
                "baseline_days": baseline_days,
                "reason": (
                    f"Transaction ${float(current_amount):,.2f} is "
                    f"{float(current_amount / avg_amount):.1f}x the customer average "
                    f"of ${float(avg_amount):,.2f}"
                ),
            }
        return False, {}

    @classmethod
    def _check_round_amounts_rule(cls, rule: MonitoringRule, user_account) -> Tuple[bool, Dict]:
        from wallets.models import Transaction

        params = rule.parameters
        count_threshold = params.get("count", ROUND_AMOUNT_COUNT_THRESHOLD)
        period_days = params.get("period_days", ROUND_AMOUNT_PERIOD_DAYS)
        divisor = Decimal(str(params.get("divisor", ROUND_AMOUNT_DIVISOR)))
        min_amount = Decimal(str(params.get("min_amount", 1000)))

        period_start = timezone.now() - timedelta(days=period_days)

        recent_txns = Transaction.objects.filter(
            wallet__user_account=user_account,
            created_at__gte=period_start,
            market_value__isnull=False,
            market_value__gte=min_amount,
        )

        round_amounts = []
        for txn in recent_txns:
            amount = txn.market_value
            if amount % divisor == Decimal("0"):
                round_amounts.append(float(amount))

        if len(round_amounts) >= count_threshold:
            return True, {
                "round_amount_count": len(round_amounts),
                "count_threshold": count_threshold,
                "divisor": float(divisor),
                "period_days": period_days,
                "round_amounts": round_amounts[:10],
                "reason": (
                    f"Found {len(round_amounts)} transactions with round amounts "
                    f"(divisible by ${float(divisor):,.0f}) in {period_days} days"
                ),
            }
        return False, {}

    @classmethod
    def _check_extreme_risk_rule(cls, rule: MonitoringRule, transaction, user_account) -> Tuple[bool, Dict]:
        from compliance.models import CustomerRiskAssessment

        if transaction is None:
            return False, {}

        latest_assessment = CustomerRiskAssessment.objects.filter(
            user_account=user_account,
            assessment_status="complete",
        ).first()

        if not latest_assessment:
            return False, {}

        if latest_assessment.overall_risk_rating != RISK_RATING_EXTREME:
            return False, {}

        amount = transaction.market_value or Decimal("0")

        return True, {
            "risk_rating": latest_assessment.overall_risk_rating,
            "risk_score": latest_assessment.total_score,
            "transaction_amount": float(amount),
            "assessment_date": latest_assessment.created_at.isoformat(),
            "reason": (
                f"Transaction by EXTREME risk customer (score: {latest_assessment.total_score}) "
                f"requires manual review per Document 2 §4.2"
            ),
            "action_required": "Manual review required before processing",
        }

    @classmethod
    def _create_alert(
        cls,
        rule: MonitoringRule,
        user_account,
        transaction,
        details: Dict,
    ) -> ComplianceAlert:
        alert_type = RULE_CODE_TO_ALERT_TYPE.get(rule.rule_code, rule.rule_code.lower().replace("-", "_"))

        return ComplianceAlert.objects.create(
            user_account=user_account,
            transaction=transaction,
            monitoring_rule=rule,
            alert_type=alert_type,
            severity=rule.alert_severity,
            triggered_rule=rule.rule_code,
            description=f"{rule.name}: {rule.description}",
            alert_data=details,
            status=ALERT_STATUS_NEW,
        )

    @classmethod
    def check_batch_patterns(cls, user_account) -> List[ComplianceAlert]:
        alerts_created = []
        pattern_rules = MonitoringRule.objects.active().pattern_rules()

        for rule in pattern_rules:
            triggered, details = cls._check_rule(rule, None, user_account)

            if triggered:
                existing = ComplianceAlert.objects.filter(
                    user_account=user_account,
                    monitoring_rule=rule,
                    status__in=[ALERT_STATUS_NEW, ALERT_STATUS_REVIEWING],
                ).exists()

                if not existing:
                    alert = cls._create_alert(
                        rule=rule,
                        user_account=user_account,
                        transaction=None,
                        details=details,
                    )
                    alerts_created.append(alert)
                    logger.info(
                        f"{LoggingContext.MONITORING} Batch rule {rule.rule_code} triggered for "
                        f"user_account {user_account.uuid}"
                    )

        return alerts_created
