from django.db import models
from django.db.models import QuerySet

from tokens.models.choices import RequestStatus


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

    def pending(self):
        """Requests still needing staff action: submitted, under review, or approved but not yet executed."""
        return self.filter(status__in=[RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW, RequestStatus.APPROVED])

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
