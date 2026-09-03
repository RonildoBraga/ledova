import logging
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

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
    ASSESSMENT_STATUS_COMPLETE,
    DORMANT_ACCOUNT_DAYS,
    HIGH_RISK_RATINGS,
    NEW_CUSTOMER_DAYS,
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
    SCREENING_RESULT_REJECTED,
    SCREENING_RESULT_REVIEW,
    SCREENING_STATUS_FAILED,
    SCREENING_THRESHOLD_AUD,
    TRANSACTION_MONITORING_WINDOW_HOURS,
)
from compliance.models import ComplianceAlert, CustomerRiskAssessment, MonitoringRule
from compliance.services.crypto_screening import CryptoScreeningService
from wallets.models import FiatTransaction, Transaction

logger = logging.getLogger(__name__)

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

RuleResult = Tuple[bool, Dict]


def is_new_customer(user_account, days: int = NEW_CUSTOMER_DAYS) -> bool:
    if not user_account.activation_date:
        return True
    return user_account.activation_date > timezone.now() - timedelta(days=days)


def _market_value(transaction) -> Decimal:
    return transaction.market_value or Decimal("0")


def _latest_complete_assessment(user_account) -> Optional[CustomerRiskAssessment]:
    return CustomerRiskAssessment.objects.filter(
        user_account=user_account, assessment_status=ASSESSMENT_STATUS_COMPLETE
    ).first()


def _has_sof_documentation(user_account) -> bool:
    director = user_account.director or user_account.user_profiles.first()
    financial_profile = getattr(director, "financial_profile", None)
    sof = financial_profile.source_of_funds if financial_profile else None
    return bool(sof) and sof != "other" and sof != ["other"]


def _check_threshold(rule, transaction, user_account) -> RuleResult:
    if transaction is None:
        return False, {}
    threshold = Decimal(str(rule.parameters.get("amount", ALERT_THRESHOLD_AUD)))
    amount = _market_value(transaction)
    if amount < threshold:
        return False, {}
    return True, {
        "amount": float(amount),
        "threshold": float(threshold),
        "currency": rule.parameters.get("currency", "AUD"),
    }


def _check_rapid_transactions(rule, transaction, user_account) -> RuleResult:
    max_transactions = rule.parameters.get("max_transactions", 5)
    period_minutes = rule.parameters.get("period_minutes", 60)
    count = Transaction.objects.filter(
        wallet__user_account=user_account,
        created_at__gte=timezone.now() - timedelta(minutes=period_minutes),
    ).count()
    if count < max_transactions:
        return False, {}
    return True, {
        "transaction_count": count,
        "threshold": max_transactions,
        "period_minutes": period_minutes,
        "reason": f"{count} transactions in {period_minutes} minutes",
    }


def _check_structuring_pattern(rule, transaction, user_account) -> RuleResult:
    params = rule.parameters
    min_transactions = params.get("min_transactions", 3)
    max_each = Decimal(str(params.get("max_each", 9999)))
    min_each = Decimal(str(params.get("min_each", 8000)))
    period_hours = params.get("period_hours", 168)
    count = Transaction.objects.filter(
        wallet__user_account=user_account,
        created_at__gte=timezone.now() - timedelta(hours=period_hours),
        market_value__gte=min_each,
        market_value__lte=max_each,
    ).count()
    if count < min_transactions:
        return False, {}
    return True, {
        "transaction_count": count,
        "min_required": min_transactions,
        "amount_range": f"${float(min_each):,.0f} - ${float(max_each):,.0f}",
        "period_hours": period_hours,
        "pattern": "potential_structuring",
    }


def _screening_trigger(transaction, user_account) -> Optional[str]:
    assessment = _latest_complete_assessment(user_account)
    if assessment and assessment.overall_risk_rating in HIGH_RISK_RATINGS:
        return "high_risk_customer"
    if _market_value(transaction) >= SCREENING_THRESHOLD_AUD:
        return "large_transaction"
    if is_new_customer(user_account):
        return "new_customer"
    return None


def _check_address(rule, transaction, user_account) -> RuleResult:
    if transaction is None:
        return False, {}
    trigger = _screening_trigger(transaction, user_account)
    if trigger is None:
        logger.debug(f"Skipping address screening for transaction {transaction.uuid}")
        return False, {}
    logger.info(f"Address screening triggered for transaction {transaction.uuid} (reason: {trigger})")
    screening = CryptoScreeningService().screen_transaction(transaction, user_account)
    if screening.status == SCREENING_STATUS_FAILED:
        verdict = "Crypto screening failed - address safety unverified"
    elif screening.result == SCREENING_RESULT_REJECTED:
        verdict = "Crypto screening flagged high-risk address"
    elif screening.result == SCREENING_RESULT_REVIEW:
        verdict = "Crypto screening requires manual review"
    else:
        return False, {}
    details = {
        "flagged_address": screening.to_address,
        "screening_id": str(screening.pk),
        "screening_trigger": trigger,
        "reason": verdict,
    }
    if screening.status == SCREENING_STATUS_FAILED:
        details["error"] = screening.error_message
    else:
        details.update(risk_score=screening.risk_score, risk_signals=screening.risk_signals)
    return True, details


def _check_sof_required(rule, transaction, user_account) -> RuleResult:
    if transaction is None:
        return False, {}
    threshold = Decimal(str(rule.parameters.get("amount", ALERT_THRESHOLD_AUD)))
    customer_age_days = rule.parameters.get("customer_age_days", 30)
    amount = _market_value(transaction)
    if not is_new_customer(user_account, days=customer_age_days) or amount < threshold:
        return False, {}
    if _has_sof_documentation(user_account):
        return False, {}
    return True, {
        "amount": float(amount),
        "threshold": float(threshold),
        "has_sof_documentation": False,
        "customer_age_days": customer_age_days,
        "reason": "High-value transaction by new customer without SOF documentation",
        "action_required": "Request source of funds documentation",
    }


def _check_aggregate_volume(rule, transaction, user_account) -> RuleResult:
    threshold = Decimal(str(rule.parameters.get("amount", AGGREGATE_VOLUME_THRESHOLD_AUD)))
    period_days = rule.parameters.get("period_days", AGGREGATE_VOLUME_PERIOD_DAYS)
    period_start = timezone.now() - timedelta(days=period_days)
    crypto_volume = Transaction.objects.filter(
        wallet__user_account=user_account, created_at__gte=period_start, market_value__isnull=False
    ).aggregate(total=Sum("market_value"))["total"] or Decimal("0")
    fiat_volume = FiatTransaction.objects.filter(
        user__userprofile__user_accounts=user_account, created_at__gte=period_start, fiat_amount__isnull=False
    ).aggregate(total=Sum("fiat_amount"))["total"] or Decimal("0")
    total_volume = crypto_volume + fiat_volume
    if total_volume < threshold:
        return False, {}
    return True, {
        "total_volume": float(total_volume),
        "crypto_volume": float(crypto_volume),
        "fiat_volume": float(fiat_volume),
        "threshold": float(threshold),
        "period_days": period_days,
        "reason": f"High aggregate volume: ${float(total_volume):,.2f} in {period_days} days",
    }


def _check_dormant_reactivation(rule, transaction, user_account) -> RuleResult:
    if transaction is None:
        return False, {}
    dormant_days = rule.parameters.get("dormant_days", DORMANT_ACCOUNT_DAYS)
    min_amount = Decimal(str(rule.parameters.get("min_amount", SCREENING_THRESHOLD_AUD)))
    amount = _market_value(transaction)
    if amount < min_amount:
        return False, {}
    previous = (
        Transaction.objects.filter(wallet__user_account=user_account, created_at__lt=transaction.created_at)
        .order_by("-created_at")
        .first()
    )
    if not previous:
        return False, {}
    days_inactive = (transaction.created_at - previous.created_at).days
    if days_inactive < dormant_days:
        return False, {}
    return True, {
        "days_inactive": days_inactive,
        "dormant_threshold": dormant_days,
        "transaction_amount": float(amount),
        "min_amount": float(min_amount),
        "last_activity": previous.created_at.isoformat(),
        "reason": f"Dormant account reactivation after {days_inactive} days with ${float(amount):,.2f} transaction",
    }


def _check_pattern_deviation(rule, transaction, user_account) -> RuleResult:
    if transaction is None:
        return False, {}
    multiplier = rule.parameters.get("multiplier", PATTERN_DEVIATION_MULTIPLIER)
    min_history = rule.parameters.get("min_history", PATTERN_DEVIATION_MIN_HISTORY)
    baseline_days = rule.parameters.get("baseline_days", PATTERN_DEVIATION_BASELINE_DAYS)
    amount = _market_value(transaction)
    if amount <= 0:
        return False, {}
    history = Transaction.objects.filter(
        wallet__user_account=user_account,
        created_at__gte=timezone.now() - timedelta(days=baseline_days),
        market_value__isnull=False,
        market_value__gt=0,
    ).exclude(uuid=transaction.uuid)
    history_count = history.count()
    if history_count < min_history:
        return False, {}
    average = history.aggregate(avg=Avg("market_value"))["avg"] or Decimal("0")
    if average <= 0 or amount < average * multiplier:
        return False, {}
    return True, {
        "transaction_amount": float(amount),
        "average_amount": float(average),
        "deviation_multiplier": multiplier,
        "deviation_threshold": float(average * multiplier),
        "historical_count": history_count,
        "baseline_days": baseline_days,
        "reason": (
            f"Transaction ${float(amount):,.2f} is {float(amount / average):.1f}x the customer average "
            f"of ${float(average):,.2f}"
        ),
    }


def _check_round_amounts(rule, transaction, user_account) -> RuleResult:
    count_threshold = rule.parameters.get("count", ROUND_AMOUNT_COUNT_THRESHOLD)
    period_days = rule.parameters.get("period_days", ROUND_AMOUNT_PERIOD_DAYS)
    divisor = Decimal(str(rule.parameters.get("divisor", ROUND_AMOUNT_DIVISOR)))
    min_amount = Decimal(str(rule.parameters.get("min_amount", 1000)))
    recent = Transaction.objects.filter(
        wallet__user_account=user_account,
        created_at__gte=timezone.now() - timedelta(days=period_days),
        market_value__isnull=False,
        market_value__gte=min_amount,
    )
    round_amounts = [float(tx.market_value) for tx in recent if tx.market_value % divisor == 0]
    if len(round_amounts) < count_threshold:
        return False, {}
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


def _check_extreme_risk(rule, transaction, user_account) -> RuleResult:
    if transaction is None:
        return False, {}
    assessment = _latest_complete_assessment(user_account)
    if not assessment or assessment.overall_risk_rating != RISK_RATING_EXTREME:
        return False, {}
    return True, {
        "risk_rating": assessment.overall_risk_rating,
        "risk_score": assessment.total_risk_score,
        "transaction_amount": float(_market_value(transaction)),
        "assessment_date": assessment.created_at.isoformat(),
        "reason": (
            f"Transaction by EXTREME risk customer (score: {assessment.total_risk_score}) "
            "requires manual review per Document 2 §4.2"
        ),
        "action_required": "Manual review required before processing",
    }


# Every checker takes (rule, transaction, user_account); transaction is None during the batch pattern sweep.
RULE_CHECKS = {
    RULE_TYPE_THRESHOLD: _check_threshold,
    RULE_TYPE_RAPID_TRANSACTIONS: _check_rapid_transactions,
    RULE_TYPE_PATTERN: _check_structuring_pattern,
    RULE_TYPE_ADDRESS: _check_address,
    RULE_TYPE_SOF_REQUIRED: _check_sof_required,
    RULE_TYPE_AGGREGATE_VOLUME: _check_aggregate_volume,
    RULE_TYPE_DORMANT_REACTIVATION: _check_dormant_reactivation,
    RULE_TYPE_PATTERN_DEVIATION: _check_pattern_deviation,
    RULE_TYPE_ROUND_AMOUNTS: _check_round_amounts,
    RULE_TYPE_EXTREME_RISK: _check_extreme_risk,
}


def check_rule(rule: MonitoringRule, transaction, user_account) -> RuleResult:
    checker = RULE_CHECKS.get(rule.rule_type)
    return checker(rule, transaction, user_account) if checker else (False, {})


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
                logger.info(f"Created {len(alerts)} alert(s) for transaction {tx.uuid}")
        except Exception:
            logger.exception(f"Error checking transaction {tx.uuid}")

    @classmethod
    def check_transaction(cls, transaction, user_account) -> List[ComplianceAlert]:
        alerts = []
        for rule in MonitoringRule.objects.active():
            triggered, details = check_rule(rule, transaction, user_account)
            if triggered:
                alerts.append(cls._create_alert(rule, user_account, transaction, details))
                logger.info(
                    f"Rule {rule.rule_code} triggered for "
                    f"user_account {user_account.uuid}, transaction {transaction.uuid}"
                )
        return alerts

    @classmethod
    def check_batch_patterns(cls, user_account) -> List[ComplianceAlert]:
        alerts = []
        for rule in MonitoringRule.objects.active().pattern_rules():
            triggered, details = check_rule(rule, None, user_account)
            already_open = ComplianceAlert.objects.filter(
                user_account=user_account,
                monitoring_rule=rule,
                status__in=[ALERT_STATUS_NEW, ALERT_STATUS_REVIEWING],
            ).exists()
            if triggered and not already_open:
                alerts.append(cls._create_alert(rule, user_account, None, details))
                logger.info(f"Batch rule {rule.rule_code} triggered for user_account {user_account.uuid}")
        return alerts

    @staticmethod
    def _create_alert(rule: MonitoringRule, user_account, transaction, details: Dict) -> ComplianceAlert:
        return ComplianceAlert.objects.create(
            user_account=user_account,
            transaction=transaction,
            monitoring_rule=rule,
            alert_type=RULE_CODE_TO_ALERT_TYPE.get(rule.rule_code, rule.rule_code.lower().replace("-", "_")),
            severity=rule.alert_severity,
            triggered_rule=rule.rule_code,
            description=f"{rule.name}: {rule.description}",
            alert_data=details,
            status=ALERT_STATUS_NEW,
        )
