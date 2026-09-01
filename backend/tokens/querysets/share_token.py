from django.db import models
from django.db.models import QuerySet


class ShareTokenQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()

        from companies.models import Company

        user_companies = Company.objects.visible_to_user(user)
        return self.filter(company__in=user_companies)

    def manageable_by_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()

        from companies.models import Company

        user_companies = Company.objects.manageable_by_user(user)
        return self.filter(company__in=user_companies)

    def deployed(self):
        return self.filter(status="deployed")

    def deployed_with_contract(self):
        return self.deployed().exclude(contract_address__isnull=True).exclude(contract_address="")

    def draft(self):
        return self.filter(status="draft")

    def with_company(self):
        return self.select_related("company")

    def search(self, query):
        if not query:
            return self
        return self.filter(
            models.Q(name__icontains=query)
            | models.Q(symbol__icontains=query)
            | models.Q(contract_address__icontains=query)
        )
