from django.db.models import Q, QuerySet
from guardian.shortcuts import get_objects_for_user


class CompanyQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        return get_objects_for_user(user, "companies.view_company", klass=self)

    def manageable_by_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        return get_objects_for_user(user, "companies.change_company", klass=self)

    def with_optimized_data(self):
        return self.prefetch_related("contacts", "documents", "whitelist_entries")

    def active(self):
        from companies.models import CompanyStatus

        return self.filter(status=CompanyStatus.ACTIVE)

    def approved(self):
        from companies.models import CompanyStatus

        return self.filter(status__in=[CompanyStatus.APPROVED, CompanyStatus.ACTIVE])

    def pending_review(self):
        from companies.models import CompanyStatus

        return self.filter(status__in=[CompanyStatus.SUBMITTED, CompanyStatus.REVIEW])

    def draft(self):
        from companies.models import CompanyStatus

        return self.filter(status=CompanyStatus.DRAFT)

    def search(self, query):
        if not query:
            return self
        return self.filter(Q(name__icontains=query) | Q(trading_name__icontains=query) | Q(acn__icontains=query))
