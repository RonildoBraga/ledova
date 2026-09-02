from django.db.models import Q, QuerySet


class CompanyQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(owner=user)

    def manageable_by_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(owner=user)

    def active(self):
        from companies.models import CompanyStatus

        return self.filter(status=CompanyStatus.ACTIVE)

    def search(self, query):
        if not query:
            return self
        return self.filter(Q(name__icontains=query) | Q(trading_name__icontains=query) | Q(acn__icontains=query))
