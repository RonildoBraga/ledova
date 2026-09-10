from django.db import models

from users.models import UserAccount


class OrderSubmissionQuerySet(models.QuerySet):
    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(owner_account__in=UserAccount.objects.visible_to_user(user))
