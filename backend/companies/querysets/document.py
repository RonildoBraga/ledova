from django.db.models import QuerySet


class CompanyDocumentQuerySet(QuerySet):

    def visible_to_user(self, user):
        from companies.models import Company

        visible_companies = Company.objects.visible_to_user(user)
        return self.filter(company__in=visible_companies)

    def manageable_by_user(self, user):
        from companies.models import Company

        manageable_companies = Company.objects.manageable_by_user(user)
        return self.filter(company__in=manageable_companies)
