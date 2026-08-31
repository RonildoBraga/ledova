import logging
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger("ledova_backend")

TRANSACTION_MONITORING_WINDOW_HOURS = 1


@receiver(post_save, sender="wallets.Transaction")
def monitor_crypto_transaction(sender, instance, created, **kwargs):
    if not created:
        return

    if instance.block_timestamp:
        # Ensure block_timestamp is a datetime object for comparison
        block_timestamp = instance.block_timestamp
        if isinstance(block_timestamp, str):
            block_timestamp = parse_datetime(block_timestamp)
        if not isinstance(block_timestamp, datetime):
            # Skip monitoring if timestamp cannot be parsed
            return

        cutoff = timezone.now() - timedelta(hours=TRANSACTION_MONITORING_WINDOW_HOURS)
        if block_timestamp < cutoff:
            logger.debug(
                f"[MONITORING_SIGNAL] Skipping historical transaction {instance.uuid} "
                f"(block_timestamp: {instance.block_timestamp})"
            )
            return

    wallet = instance.wallet
    if not wallet:
        return

    user_account = getattr(wallet, "user_account", None)
    if not user_account:
        logger.debug(f"[MONITORING_SIGNAL] No user_account for transaction {instance.uuid}")
        return

    from compliance.services.transaction_monitoring import TransactionMonitoringService

    try:
        alerts = TransactionMonitoringService.check_transaction(
            transaction=instance,
            user_account=user_account,
        )
        if alerts:
            logger.info(f"[MONITORING_SIGNAL] Created {len(alerts)} alert(s) for transaction {instance.uuid}")
    except Exception as e:
        logger.error(
            f"[MONITORING_SIGNAL] Error checking transaction {instance.uuid}: {str(e)}",
            exc_info=True,
        )


@receiver(post_save, sender="wallets.FiatTransaction")
def monitor_fiat_transaction(sender, instance, created, **kwargs):
    if not created:
        return

    user = instance.user
    if not user:
        return

    try:
        user_profile = user.userprofile
    except AttributeError:
        logger.debug(f"[MONITORING_SIGNAL] No user_profile for fiat transaction {instance.uuid}")
        return

    user_account = user_profile.user_accounts.first()
    if not user_account:
        logger.debug(f"[MONITORING_SIGNAL] No user_account for fiat transaction {instance.uuid}")
        return

    from compliance.services.transaction_monitoring import TransactionMonitoringService

    try:
        alerts = TransactionMonitoringService.check_fiat_transaction(
            fiat_transaction=instance,
            user_account=user_account,
        )
        if alerts:
            logger.info(f"[MONITORING_SIGNAL] Created {len(alerts)} alert(s) for fiat transaction {instance.uuid}")
    except Exception as e:
        logger.error(
            f"[MONITORING_SIGNAL] Error checking fiat transaction {instance.uuid}: {str(e)}",
            exc_info=True,
        )


@receiver(post_save, sender="users.UserAccount")
def create_pending_assessment(sender, instance, created, **kwargs):
    if not created:
        return

    from compliance.services.risk_assessment import RiskAssessmentService

    try:
        RiskAssessmentService.create_pending_assessment(user_account=instance)
        logger.info(f"[RISK_ASSESSMENT_SIGNAL] Created pending assessment for user_account {instance.uuid}")
    except Exception as e:
        logger.error(
            f"[RISK_ASSESSMENT_SIGNAL] Error creating pending assessment for user_account {instance.uuid}: {str(e)}",
            exc_info=True,
        )

