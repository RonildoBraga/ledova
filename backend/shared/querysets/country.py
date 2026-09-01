from django.db import models
from django.db.models import QuerySet


class CountryQuerySet(QuerySet):

    def filter_by_name(self, name):
        if name:
            return self.filter(name__icontains=name)
        return self

    def filter_by_code(self, code):
        if code:
            return self.filter(code__iexact=code)
        return self

    def filter_by_dial_code(self, dial_code):
        if dial_code:
            return self.filter(dial_code=dial_code)
        return self

    def search(self, search_query):
        if search_query:
            return self.filter(models.Q(name__icontains=search_query) | models.Q(code__icontains=search_query))
        return self

    def filter_available(self, is_available=True):
        """Kept for manager proxy."""
        return self.filter(is_available=is_available)

    def available_countries(self):
        return self.filter(is_available=True)

    def with_dial_code(self):
        return self.filter(dial_code__isnull=False).exclude(dial_code="")
