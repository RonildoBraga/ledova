from django.db.models import QuerySet


class CompanyDocumentQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self

        from companies.models import Company

        visible_companies = Company.objects.visible_to_user(user)
        return self.filter(company__in=visible_companies)

    def manageable_by_user(self, user):
        if user.is_superuser or user.is_staff:
            return self

        from companies.models import Company

        manageable_companies = Company.objects.manageable_by_user(user)
        return self.filter(company__in=manageable_companies)

    def with_optimized_data(self):
        return self.select_related("company", "verified_by")

    def verified(self):
        return self.filter(is_verified=True)

    def unverified(self):
        return self.filter(is_verified=False)

    def for_company(self, company):
        return self.filter(company=company)

    def of_type(self, document_type):
        return self.filter(document_type=document_type)

    def required_for_listing(self):
        from companies.models import LISTING_REQUIRED_DOCUMENTS

        required_types = [dt.value for dt in LISTING_REQUIRED_DOCUMENTS]
        return self.filter(document_type__in=required_types)
