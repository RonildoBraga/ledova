from django.db.models import QuerySet


class AlertChecklistItemQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user and (user.is_superuser or user.is_staff):
            return self
        return self.none()

    def completed(self):
        return self.filter(is_completed=True)

    def pending(self):
        return self.filter(is_completed=False, is_skipped=False)

    def required(self):
        return self.filter(step__is_required=True)

    def required_pending(self):
        return self.required().pending()

    def pending_required_for_alert(self, alert):
        return self.filter(alert=alert).required_pending().order_by("step__order")
