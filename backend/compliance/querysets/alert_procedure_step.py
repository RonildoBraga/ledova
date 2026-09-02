from django.db.models import QuerySet


class AlertProcedureStepQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user and (user.is_superuser or user.is_staff):
            return self
        return self.none()

    def required(self):
        return self.filter(is_required=True)
