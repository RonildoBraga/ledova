from django.db import models

from shared.models import BaseModel


class Waitlist(BaseModel):
    email = models.EmailField(
        unique=True,
        help_text="Email address of the user signing up for the waitlist",
    )
    subscribed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the user subscribed to the waitlist",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the waitlist subscription is active",
    )

    class Meta:
        db_table = "accounts_waitlist"
        ordering = ["-subscribed_at"]
        verbose_name = "Waitlist Entry"
        verbose_name_plural = "Waitlist Entries"

    def __str__(self):
        return f"Waitlist: {self.email}"
