from django.db.models import QuerySet


class AlertProcedureTemplateQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user and (user.is_superuser or user.is_staff):
            return self
        return self.none()

    def active(self):
        return self.filter(is_active=True)

    def for_alert(self, alert):
        return self.active().filter(alert_type=alert.alert_type).first()
