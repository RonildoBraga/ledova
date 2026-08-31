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
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


class RiskAssessmentService:
    @classmethod
    def create_pending_assessment(cls, user_account) -> CustomerRiskAssessment:
        assessment = CustomerRiskAssessment.objects.create(
            user_account=user_account,
            assessment_status=ASSESSMENT_STATUS_PENDING,
            is_automated=True,
            assessment_reason="Pending verification completion",
        )

        logger.info(f"{LoggingContext.RISK_ASSESSMENT} Created pending assessment for user_account {user_account.uuid}")

        return assessment

    @classmethod
    def calculate_and_create(
        cls,
        user_account,
        pep_data: Optional[Dict] = None,
    ) -> CustomerRiskAssessment:
        director = user_account.director
        if not director:
            director = user_account.user_profiles.first()

        if not director:
            logger.warning(
                f"{LoggingContext.RISK_ASSESSMENT} No user profile found for user_account {user_account.uuid}"
            )
            return cls._create_incomplete_assessment(user_account, "No user profile available")

        customer_score, customer_factors = cls._calculate_customer_risk(director, pep_data)
        geographic_score, geographic_factors = cls._calculate_geographic_risk(director)
        product_score = 1

        total_score = customer_score + geographic_score + product_score
        overall_rating = cls._determine_overall_rating(total_score)

        assessment_reason = cls._build_assessment_reason(
            customer_score,
            customer_factors,
            geographic_score,
            geographic_factors,
            product_score,
            total_score,
            overall_rating,
        )

        now = timezone.now()
        valid_until = now + timedelta(days=RISK_REVIEW_PERIOD_MONTHS * 30)
        next_review = valid_until

        existing = CustomerRiskAssessment.objects.filter(
            user_account=user_account,
            assessment_status=ASSESSMENT_STATUS_PENDING,
        ).first()

        pep_type = pep_data.get("pep_type", PEP_TYPE_NONE) if pep_data else PEP_TYPE_NONE

        if existing:
            existing.assessment_status = ASSESSMENT_STATUS_COMPLETE
            existing.overall_risk_rating = overall_rating
            existing.customer_risk_score = customer_score
            existing.geographic_risk_score = geographic_score
            existing.product_risk_score = product_score
            existing.pep_type = pep_type
            existing.pep_details = pep_data
            existing.high_risk_country = "high_risk_country" in geographic_factors
            existing.high_risk_occupation = "high_risk_occupation" in customer_factors
            existing.assessment_reason = assessment_reason
            existing.valid_from = now
            existing.valid_until = valid_until
            existing.next_review_date = next_review
            existing.save()

            logger.info(
                f"{LoggingContext.RISK_ASSESSMENT} Updated assessment for user_account {user_account.uuid}: "
                f"{overall_rating.upper()} (score: {total_score})"
            )
            return existing

        assessment = CustomerRiskAssessment.objects.create(
            user_account=user_account,
            assessment_status=ASSESSMENT_STATUS_COMPLETE,
            overall_risk_rating=overall_rating,
            customer_risk_score=customer_score,
            geographic_risk_score=geographic_score,
            product_risk_score=product_score,
            pep_type=pep_type,
            pep_details=pep_data,
            high_risk_country="high_risk_country" in geographic_factors,
            high_risk_occupation="high_risk_occupation" in customer_factors,
            assessment_reason=assessment_reason,
            is_automated=True,
            valid_from=now,
            valid_until=valid_until,
            next_review_date=next_review,
        )

        logger.info(
            f"{LoggingContext.RISK_ASSESSMENT} Created assessment for user_account {user_account.uuid}: "
            f"{overall_rating.upper()} (score: {total_score})"
        )

        return assessment

    @classmethod
    def _calculate_customer_risk(cls, user_profile, pep_data: Optional[Dict]) -> Tuple[int, list]:
        score = 1
        factors = []

        pep_type = PEP_TYPE_NONE
        if pep_data:
            pep_type = pep_data.get("pep_type", PEP_TYPE_NONE)

        if pep_type == PEP_TYPE_DOMESTIC:
            score += DOMESTIC_PEP_RISK_ADJUSTMENT
            factors.append("domestic_pep")

        financial_profile = getattr(user_profile, "financial_profile", None)
        if financial_profile and financial_profile.occupation:
            occupation_lower = financial_profile.occupation.lower().replace(" ", "_")
            if any(high_risk in occupation_lower for high_risk in HIGH_RISK_OCCUPATIONS):
                score += 1
                factors.append("high_risk_occupation")

        if financial_profile and financial_profile.source_of_funds:
            sof = financial_profile.source_of_funds
            if (isinstance(sof, list) and "other" in sof) or sof == "other":
                score += 1
                factors.append("unspecified_source_of_funds")

        return score, factors

    @classmethod
    def _calculate_geographic_risk(cls, user_profile) -> Tuple[int, list]:
        score = 1
        factors = []

        country = user_profile.citizenship_country
        if not country:
            return 2, ["unknown_country"]

        country_code = country.upper() if isinstance(country, str) else str(country).upper()

        if country_code == "AU":
            factors.append("domestic")
        else:
            factors.append("foreign_country")

        if getattr(user_profile, "used_foreign_passport", False):
            score += 1
            factors.append("foreign_passport")

        return score, factors

    @classmethod
    def _determine_overall_rating(cls, total_score: int) -> str:
        if total_score <= RISK_THRESHOLD_LOW:
            return RISK_RATING_LOW
        elif total_score <= RISK_THRESHOLD_MEDIUM:
            return RISK_RATING_MEDIUM
        elif total_score <= RISK_THRESHOLD_HIGH:
            return RISK_RATING_HIGH
        else:
            return RISK_RATING_EXTREME

    @classmethod
    def _build_assessment_reason(
        cls,
        customer_score: int,
        customer_factors: list,
        geographic_score: int,
        geographic_factors: list,
        product_score: int,
        total_score: int,
        overall_rating: str,
    ) -> str:
        lines = [
            "Automated risk assessment completed.",
            "",
            f"Customer Risk Score: {customer_score}/5",
        ]
        if customer_factors:
            lines.append(f"  Factors: {', '.join(customer_factors)}")

        lines.extend(
            [
                f"Geographic Risk Score: {geographic_score}/5",
            ]
        )
        if geographic_factors:
            lines.append(f"  Factors: {', '.join(geographic_factors)}")

        lines.extend(
            [
                f"Product Risk Score: {product_score}/5 (standard crypto services)",
                "",
                f"Total Score: {total_score}/15",
                f"Overall Rating: {overall_rating.upper()}",
            ]
        )

        return "\n".join(lines)

    @classmethod
    def _create_incomplete_assessment(cls, user_account, reason: str) -> CustomerRiskAssessment:
        return CustomerRiskAssessment.objects.create(
            user_account=user_account,
            assessment_status=ASSESSMENT_STATUS_INCOMPLETE,
            is_automated=True,
            assessment_reason=f"Incomplete: {reason}",
        )
