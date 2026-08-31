from django.db import models


class DocumentQuerySet(models.QuerySet):
    def for_user(self, user) -> "DocumentQuerySet":
        return self.filter(uploaded_by=user)

    def with_latest_extraction(self) -> "DocumentQuerySet":
        # `extractions` is the reverse relation; ordering on the model
        # Meta is `-created_at`, so prefetch picks them up newest-first.
        return self.prefetch_related("extractions")
