import logging

from django.db import transaction

from users.models.investor_classification import InvestorClassification

logger = logging.getLogger(__name__)


@transaction.atomic
def transition_classification(classification: InvestorClassification, method: str, **kwargs) -> InvestorClassification:
    getattr(classification, method)(**kwargs)
    logger.info(f"Investor classification {classification.uuid}: {method} by {kwargs.get('reviewed_by')}")
    return classification
