from django.db.models import QuerySet
from django.utils import timezone
from guardian.shortcuts import get_objects_for_user


class CustomUserQuerySet(QuerySet):
    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        return get_objects_for_user(user, "view_customuser", klass=self)

    def active_users(self):
        return self.filter(is_active=True)

    def verified_users(self):
        return self.filter(is_email_verified=True)

    def staff_users(self):
        return self.filter(is_staff=True)

    def unverified_users(self):
        return self.filter(is_email_verified=False)

    def recently_joined(self, days=30):
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        return self.filter(date_joined__gte=cutoff_date)

    def inactive_users(self, days=90):
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        return self.filter(last_login__lt=cutoff_date)
