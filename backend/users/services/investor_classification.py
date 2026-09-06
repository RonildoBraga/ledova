import logging

from django.db import transaction

from users.models.investor_classification import InvestorClassification

logger = logging.getLogger(__name__)


@transaction.atomic
def transition_classification(classification: InvestorClassification, method: str, **kwargs) -> InvestorClassification:
    getattr(classification, method)(**kwargs)
    logger.info(f"Investor classification {classification.uuid}: {method} by {kwargs.get('reviewed_by')}")
    return classification


def purge_evidence(classification: InvestorClassification) -> InvestorClassification:
    classification.evidence_file.delete(save=False)
    classification.save(update_fields=["evidence_file", "updated_at"])
    return classification


def purge_expired_evidence(moment, limit) -> dict:
    purged = 0
    failed = 0

    for classification in InvestorClassification.objects.evidence_purgeable(moment)[:limit]:
        try:
            purge_evidence(classification)
        except Exception:
            failed += 1
            logger.error(f"Evidence purge failed for classification {classification.uuid}", exc_info=True)
            continue
        purged += 1
        logger.info(f"Evidence purged for classification {classification.uuid} past its retention horizon")

    return {"purged": purged, "failed": failed}
