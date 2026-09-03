import logging
from typing import List, Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q

from companies.exceptions import (
    DuplicateReviewerException,
    InsufficientReviewersException,
    InvalidReviewDecisionException,
    InvalidReviewStateException,
    ReviewAlreadyCompletedException,
)
from companies.models import (
    ApplicationReview,
    Company,
    CompanyStatus,
    ReviewDecision,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class ReviewService:
    @staticmethod
    @transaction.atomic
    def assign_reviewers(
        company: Company,
        reviewers: List[User],
        assigned_by: Optional[User] = None,
    ) -> List[ApplicationReview]:
        if len(reviewers) != 2:
            raise InsufficientReviewersException()

        if reviewers[0] == reviewers[1]:
            raise DuplicateReviewerException()

        if company.status not in [CompanyStatus.SUBMITTED, CompanyStatus.REVIEW]:
            raise InvalidReviewStateException(
                f"Cannot assign reviewers: company status is '{company.get_status_display()}'"
            )

        ApplicationReview.objects.filter(
            company=company,
            decision=ReviewDecision.PENDING,
        ).delete()

        reviews = []
        for i, reviewer in enumerate(reviewers, start=1):
            review = ApplicationReview.objects.create(
                company=company,
                reviewer=reviewer,
                review_order=i,
                assigned_by=assigned_by,
            )
            reviews.append(review)
            logger.info(f"Assigned reviewer {i}: {reviewer.email} for {company.name}")

        return reviews

    @staticmethod
    @transaction.atomic
    def auto_assign_reviewers(
        company: Company,
        assigned_by: Optional[User] = None,
    ) -> List[ApplicationReview]:
        staff = (
            User.objects.filter(is_staff=True, is_active=True)
            .annotate(
                pending_count=Count(
                    "company_reviews",
                    filter=Q(company_reviews__decision=ReviewDecision.PENDING),
                )
            )
            .order_by("pending_count")
        )

        if assigned_by and assigned_by.is_staff:
            staff = staff.exclude(pk=assigned_by.pk)

        selected = list(staff[:2])

        if len(selected) < 2:
            raise InsufficientReviewersException(
                f"Not enough available staff for review assignment. Found: {len(selected)}"
            )

        return ReviewService.assign_reviewers(company, selected, assigned_by)

    @staticmethod
    @transaction.atomic
    def record_decision(
        review: ApplicationReview,
        decision: str,
        reason: str = "",
    ) -> ApplicationReview:
        if review.decision != ReviewDecision.PENDING:
            raise ReviewAlreadyCompletedException()

        if decision == ReviewDecision.APPROVED:
            review.approve(reason)
        elif decision == ReviewDecision.REJECTED:
            review.reject(reason)
        elif decision == ReviewDecision.RECUSED:
            review.recuse(reason)
        else:
            raise InvalidReviewDecisionException(decision)

        logger.info(f"Reviewer {review.reviewer.email} decision for {review.company.name}: {decision}")

        ReviewService.check_and_finalize(review.company)

        return review

    @staticmethod
    @transaction.atomic
    def check_and_finalize(company: Company) -> Optional[str]:
        if company.status != CompanyStatus.REVIEW:
            return None

        reviews = ApplicationReview.objects.filter(company=company).order_by("review_order")

        if reviews.count() != 2:
            logger.warning(f"Company {company.name} does not have exactly 2 reviews assigned")
            return None

        decisions = list(reviews.values_list("decision", flat=True))

        recused_count = decisions.count(ReviewDecision.RECUSED)
        if recused_count > 0:
            logger.info(f"Company {company.name}: {recused_count} reviewer(s) recused, need replacement")
            return "needs_replacement"

        if ReviewDecision.REJECTED in decisions:
            rejecting_review = reviews.filter(decision=ReviewDecision.REJECTED).first()
            company.reject(
                reason=rejecting_review.decision_reason or "Rejected by reviewer",
                rejected_by=rejecting_review.reviewer,
            )
            logger.info(f"Company {company.name}: REJECTED by reviewer")
            return "rejected"

        if decisions.count(ReviewDecision.APPROVED) == 2:
            approving_review = reviews.filter(decision=ReviewDecision.APPROVED).last()
            company.approve(approved_by=approving_review.reviewer)
            logger.info(f"Company {company.name}: APPROVED by both reviewers")
            return "approved"

        pending_count = decisions.count(ReviewDecision.PENDING)
        logger.info(f"Company {company.name}: {pending_count} review(s) still pending")
        return None
