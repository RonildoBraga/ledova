import logging
from datetime import timedelta
from typing import Dict, Optional, Tuple

from django.utils import timezone

from compliance.constants import (
    ASSESSMENT_STATUS_COMPLETE,
    ASSESSMENT_STATUS_INCOMPLETE,
    ASSESSMENT_STATUS_PENDING,
    DOMESTIC_PEP_RISK_ADJUSTMENT,
    HIGH_RISK_OCCUPATIONS,
    PEP_TYPE_DOMESTIC,
    PEP_TYPE_NONE,
    RISK_RATING_EXTREME,
    RISK_RATING_HIGH,
    RISK_RATING_LOW,
    RISK_RATING_MEDIUM,
    RISK_REVIEW_PERIOD_MONTHS,
    RISK_THRESHOLD_HIGH,
    RISK_THRESHOLD_LOW,
    RISK_THRESHOLD_MEDIUM,
)
from compliance.models import CustomerRiskAssessment

logger = logging.getLogger(__name__)


RATING_BY_MAX_SCORE = (
    (RISK_THRESHOLD_LOW, RISK_RATING_LOW),
    (RISK_THRESHOLD_MEDIUM, RISK_RATING_MEDIUM),
    (RISK_THRESHOLD_HIGH, RISK_RATING_HIGH),
)
PRODUCT_RISK_SCORE = 1


def overall_rating(total_score: int) -> str:
    for max_score, rating in RATING_BY_MAX_SCORE:
        if total_score <= max_score:
            return rating
    return RISK_RATING_EXTREME


def customer_risk(user_profile, pep_data: Optional[Dict]) -> Tuple[int, list]:
    score, factors = 1, []
    if (pep_data or {}).get("pep_type", PEP_TYPE_NONE) == PEP_TYPE_DOMESTIC:
        score += DOMESTIC_PEP_RISK_ADJUSTMENT
        factors.append("domestic_pep")
    financial_profile = getattr(user_profile, "financial_profile", None)
    occupation = (financial_profile.occupation or "").lower().replace(" ", "_") if financial_profile else ""
    if any(high_risk in occupation for high_risk in HIGH_RISK_OCCUPATIONS):
        score += 1
        factors.append("high_risk_occupation")
    sof = financial_profile.source_of_funds if financial_profile else None
    if sof == "other" or (isinstance(sof, list) and "other" in sof):
        score += 1
        factors.append("unspecified_source_of_funds")
    return score, factors


def geographic_risk(user_profile) -> Tuple[int, list]:
    country = user_profile.citizenship_country
    if not country:
        return 2, ["unknown_country"]
    score = 1
    factors = ["domestic" if (country.code or "").upper() == "AU" else "foreign_country"]
    if user_profile.used_foreign_passport:
        score += 1
        factors.append("foreign_passport")
    return score, factors


def assessment_reason(customer_score, customer_factors, geographic_score, geographic_factors, total, rating) -> str:
    lines = ["Automated risk assessment completed.", "", f"Customer Risk Score: {customer_score}/5"]
    if customer_factors:
        lines.append(f"  Factors: {', '.join(customer_factors)}")
    lines.append(f"Geographic Risk Score: {geographic_score}/5")
    if geographic_factors:
        lines.append(f"  Factors: {', '.join(geographic_factors)}")
    lines += [
        f"Product Risk Score: {PRODUCT_RISK_SCORE}/5 (standard crypto services)",
        "",
        f"Total Score: {total}/15",
        f"Overall Rating: {rating.upper()}",
    ]
    return "\n".join(lines)


class RiskAssessmentService:
    @staticmethod
    def create_pending_assessment(user_account) -> CustomerRiskAssessment:
        assessment = CustomerRiskAssessment.objects.create(
            user_account=user_account,
            assessment_status=ASSESSMENT_STATUS_PENDING,
            is_automated=True,
            assessment_reason="Pending verification completion",
        )
        logger.info(f"Created pending assessment for user_account {user_account.uuid}")
        return assessment

    @staticmethod
    def calculate_and_create(user_account, pep_data: Optional[Dict] = None) -> CustomerRiskAssessment:
        director = user_account.director or user_account.user_profiles.first()
        if not director:
            logger.warning(f"No user profile found for user_account {user_account.uuid}")
            return CustomerRiskAssessment.objects.create(
                user_account=user_account,
                assessment_status=ASSESSMENT_STATUS_INCOMPLETE,
                is_automated=True,
                assessment_reason="Incomplete: No user profile available",
            )

        customer_score, customer_factors = customer_risk(director, pep_data)
        geographic_score, geographic_factors = geographic_risk(director)
        total = customer_score + geographic_score + PRODUCT_RISK_SCORE
        rating = overall_rating(total)
        now = timezone.now()
        valid_until = now + timedelta(days=RISK_REVIEW_PERIOD_MONTHS * 30)
        values = {
            "assessment_status": ASSESSMENT_STATUS_COMPLETE,
            "overall_risk_rating": rating,
            "customer_risk_score": customer_score,
            "geographic_risk_score": geographic_score,
            "product_risk_score": PRODUCT_RISK_SCORE,
            "pep_type": (pep_data or {}).get("pep_type", PEP_TYPE_NONE),
            "pep_details": pep_data,
            "high_risk_occupation": "high_risk_occupation" in customer_factors,
            "assessment_reason": assessment_reason(
                customer_score, customer_factors, geographic_score, geographic_factors, total, rating
            ),
            "valid_from": now,
            "valid_until": valid_until,
            "next_review_date": valid_until,
        }

        assessment = CustomerRiskAssessment.objects.filter(
            user_account=user_account, assessment_status=ASSESSMENT_STATUS_PENDING
        ).first()
        if assessment:
            for field, value in values.items():
                setattr(assessment, field, value)
            assessment.save()
        else:
            assessment = CustomerRiskAssessment.objects.create(user_account=user_account, is_automated=True, **values)

        logger.info(f"Assessed user_account {user_account.uuid}: {rating.upper()} (score: {total})")
        return assessment
