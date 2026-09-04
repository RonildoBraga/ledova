from django.db.models import QuerySet


class ShareIssuanceRequestQuerySet(QuerySet):

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
