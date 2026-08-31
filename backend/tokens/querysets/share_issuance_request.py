from django.db import models
from django.db.models import QuerySet
from guardian.shortcuts import get_objects_for_user


class ShareIssuanceRequestQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None:
            return self.none()

        if user.is_staff or user.is_superuser:
            return self

        from companies.models import Company

        user_companies = get_objects_for_user(
            user,
            "companies.view_company",
            klass=Company,
            accept_global_perms=False,
        )
        return self.filter(token__company__in=user_companies)

    def manageable_by_user(self, user):
        if user is None:
            return self.none()

        if user.is_staff or user.is_superuser:
            return self

        from companies.models import Company

        user_companies = get_objects_for_user(
            user,
            "companies.change_company",
            klass=Company,
            accept_global_perms=False,
        )
        return self.filter(token__company__in=user_companies)

    def pending_approval(self):
        from tokens.models.choices import IssuanceRequestStatus

        return self.filter(status=IssuanceRequestStatus.PENDING_APPROVAL)

    def under_review(self):
        from tokens.models.choices import IssuanceRequestStatus

        return self.filter(status=IssuanceRequestStatus.UNDER_REVIEW)

    def pending_review(self):
        from tokens.models.choices import IssuanceRequestStatus

        return self.filter(
            status__in=[
                IssuanceRequestStatus.PENDING_APPROVAL,
                IssuanceRequestStatus.UNDER_REVIEW,
            ]
        )

    def approved(self):
        from tokens.models.choices import IssuanceRequestStatus

        return self.filter(status=IssuanceRequestStatus.APPROVED)

    def rejected(self):
        from tokens.models.choices import IssuanceRequestStatus

        return self.filter(status=IssuanceRequestStatus.REJECTED)

    def executing(self):
        from tokens.models.choices import IssuanceRequestStatus

        return self.filter(status=IssuanceRequestStatus.EXECUTING)

    def executed(self):
        from tokens.models.choices import IssuanceRequestStatus

        return self.filter(status=IssuanceRequestStatus.EXECUTED)

    def failed(self):
        from tokens.models.choices import IssuanceRequestStatus

        return self.filter(status=IssuanceRequestStatus.FAILED)

    def actionable(self):
        from tokens.models.choices import IssuanceRequestStatus

        return self.filter(
            status__in=[
                IssuanceRequestStatus.PENDING_APPROVAL,
                IssuanceRequestStatus.UNDER_REVIEW,
                IssuanceRequestStatus.APPROVED,
            ]
        )

    def ready_for_execution(self):
        from tokens.models.choices import IssuanceRequestStatus

        return self.filter(status=IssuanceRequestStatus.APPROVED)

    def can_retry(self):
        from tokens.models.choices import IssuanceRequestStatus

        return self.filter(status=IssuanceRequestStatus.FAILED)

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
            | models.Q(reason__icontains=query)
            | models.Q(recipient_address__icontains=query)
        )
