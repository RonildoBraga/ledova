from django.db import models
from django.db.models import QuerySet


class CapitalIncreaseRequestQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()

        from companies.models import Company

        user_companies = Company.objects.visible_to_user(user)
        return self.filter(token__company__in=user_companies)

    def manageable_by_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()

        from companies.models import Company

        user_companies = Company.objects.manageable_by_user(user)
        return self.filter(token__company__in=user_companies)

    def draft(self):
        from tokens.models.choices import CapitalIncreaseStatus

        return self.filter(status=CapitalIncreaseStatus.DRAFT)

    def submitted(self):
        from tokens.models.choices import CapitalIncreaseStatus

        return self.filter(status=CapitalIncreaseStatus.SUBMITTED)

    def under_review(self):
        from tokens.models.choices import CapitalIncreaseStatus

        return self.filter(status=CapitalIncreaseStatus.UNDER_REVIEW)

    def pending_review(self):
        from tokens.models.choices import CapitalIncreaseStatus

        return self.filter(
            status__in=[
                CapitalIncreaseStatus.SUBMITTED,
                CapitalIncreaseStatus.UNDER_REVIEW,
            ]
        )

    def approved(self):
        from tokens.models.choices import CapitalIncreaseStatus

        return self.filter(status=CapitalIncreaseStatus.APPROVED)

    def rejected(self):
        from tokens.models.choices import CapitalIncreaseStatus

        return self.filter(status=CapitalIncreaseStatus.REJECTED)

    def executing(self):
        from tokens.models.choices import CapitalIncreaseStatus

        return self.filter(status=CapitalIncreaseStatus.EXECUTING)

    def executed(self):
        from tokens.models.choices import CapitalIncreaseStatus

        return self.filter(status=CapitalIncreaseStatus.EXECUTED)

    def failed(self):
        from tokens.models.choices import CapitalIncreaseStatus

        return self.filter(status=CapitalIncreaseStatus.FAILED)

    def actionable(self):
        from tokens.models.choices import CapitalIncreaseStatus

        return self.filter(
            status__in=[
                CapitalIncreaseStatus.DRAFT,
                CapitalIncreaseStatus.SUBMITTED,
                CapitalIncreaseStatus.UNDER_REVIEW,
                CapitalIncreaseStatus.APPROVED,
            ]
        )

    def ready_for_execution(self):
        from tokens.models.choices import CapitalIncreaseStatus

        return self.filter(status=CapitalIncreaseStatus.APPROVED)

    def can_retry(self):
        from tokens.models.choices import CapitalIncreaseStatus

        return self.filter(status=CapitalIncreaseStatus.FAILED)

    def with_relations(self):
        return self.select_related(
            "token",
            "token__company",
            "submitted_by",
            "reviewed_by",
            "executed_issuance",
        )

    def search(self, query):
        if not query:
            return self
        return self.filter(
            models.Q(token__symbol__icontains=query)
            | models.Q(token__name__icontains=query)
            | models.Q(token__company__name__icontains=query)
            | models.Q(purpose__icontains=query)
            | models.Q(board_resolution_reference__icontains=query)
        )
