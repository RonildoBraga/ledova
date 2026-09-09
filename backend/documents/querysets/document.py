from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class DocumentQuerySet(models.QuerySet):
    def visible_to_user(self, user) -> "DocumentQuerySet":
        from users.models import InvestorClassification

        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(uploaded_by=user).filter(
            models.Q(classification__isnull=True)
            | models.Q(classification__in=InvestorClassification.objects.visible_to_user(user))
        )

    def retention_due(self, moment):
        from users.models import InvestorClassification

        due = models.Q(classification__in=InvestorClassification.objects.past_evidence_horizon(moment))
        days = settings.UNATTACHED_DOCUMENT_RETENTION_DAYS
        if days:
            due |= models.Q(classification__isnull=True, created_at__lte=moment - timedelta(days=days))
        return self.filter(due, purged_at__isnull=True)

    def with_available_content(self):
        return (
            self.filter(purged_at__isnull=True)
            .exclude(file="")
            .exclude(pk__in=self.retention_due(timezone.now()).values("pk"))
        )
