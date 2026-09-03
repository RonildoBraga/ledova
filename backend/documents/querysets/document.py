from django.db import models


class DocumentQuerySet(models.QuerySet):
    def for_user(self, user) -> "DocumentQuerySet":
        return self.filter(uploaded_by=user)
