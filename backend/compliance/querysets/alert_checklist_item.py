from django.db.models import QuerySet
from django.utils import timezone


class AlertChecklistItemQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user and (user.is_superuser or user.is_staff):
            return self
        return self.none()

    def completed(self):
        return self.filter(is_completed=True)

    def pending(self):
        return self.filter(is_completed=False, is_skipped=False)

    def skipped(self):
        return self.filter(is_skipped=True)

    def required(self):
        return self.filter(step__is_required=True)

    def optional(self):
        return self.filter(step__is_required=False)

    def required_pending(self):
        return self.required().pending()

    def completed_today(self):
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.filter(completed_at__gte=today_start)

    def with_notes(self):
        return self.exclude(notes="")
