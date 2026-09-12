from django.utils import timezone

from shared.db import CarriedByThePolicy


class NotificationQuerySet(CarriedByThePolicy):

    def unread(self):
        return self.filter(is_read=False)

    def not_archived(self):
        return self.filter(is_archived=False)

    def mark_all_read(self):
        return self.unread().update(is_read=True, read_at=timezone.now())

    def with_optimized_data(self):
        return self.select_related("user")
