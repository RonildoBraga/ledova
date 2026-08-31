from django.db.models import QuerySet
from django.utils import timezone


class UserTokenQuerySet(QuerySet):
    def filter_by_user(self, user):
        if user:
            return self.filter(user=user)
        return self

    def filter_active(self, is_active=True):
        return self.filter(is_active=is_active)

    def filter_by_device_info(self, ip_address=None, user_agent=None):
        """Kept for manager proxy."""
        queryset = self
        if ip_address:
            queryset = queryset.filter(ip_address=ip_address)
        if user_agent:
            queryset = queryset.filter(user_agent__icontains=user_agent)
        return queryset

    def filter_by_date_range(self, start_date=None, end_date=None):
        """Kept for manager proxy."""
        queryset = self
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        return queryset

    def get_by_refresh_token(self, refresh_token):
        if refresh_token:
            try:
                return self.get(refresh_token=refresh_token, is_active=True)
            except self.model.DoesNotExist:
                return None
        return None

    def get_active_token_for_user(self, user):
        return self.filter(user=user, is_active=True).first()

    def get_by_active_access_token(self, access_token):
        if access_token:
            try:
                return self.get(access_token=access_token, is_active=True)
            except self.model.DoesNotExist:
                return None
        return None

    def get_expired_tokens(self):
        return self.filter(is_active=True, expires_at__lt=timezone.now())

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        return self.filter(user=user)
