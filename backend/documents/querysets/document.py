from django.db import models


class DocumentQuerySet(models.QuerySet):
    def visible_to_user(self, user) -> "DocumentQuerySet":
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(uploaded_by=user)
