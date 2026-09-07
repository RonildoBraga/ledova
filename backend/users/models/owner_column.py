from django.db import models


class DerivesOwnerFromProfile(models.Model):

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.user_id is None and self.user_profile_id is not None:
            self.user_id = self.user_profile.user_id
        super().save(*args, **kwargs)
