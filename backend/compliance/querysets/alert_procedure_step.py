from django.db.models import QuerySet


class AlertProcedureStepQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user and (user.is_superuser or user.is_staff):
            return self
        return self.none()

    def required(self):
        return self.filter(is_required=True)

    def optional(self):
        return self.filter(is_required=False)

    def conditional(self):
        return self.exclude(condition="")

    def unconditional(self):
        return self.filter(condition="")

    def for_active_templates(self):
        return self.filter(template__is_active=True)
