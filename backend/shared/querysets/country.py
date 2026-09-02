from django.db import models
from django.db.models import QuerySet


class CountryQuerySet(QuerySet):

    def search(self, search_query):
        if search_query:
            return self.filter(models.Q(name__icontains=search_query) | models.Q(code__icontains=search_query))
        return self
