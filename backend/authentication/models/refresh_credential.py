from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from authentication.security.v2_credentials import refresh_secret_matches
from shared.models import BaseModel


class RefreshCredential(BaseModel):
    session = models.ForeignKey(
        "authentication.AuthSession",
        on_delete=models.CASCADE,
        related_name="refresh_credentials",
    )
    secret_digest = models.BinaryField(max_length=32, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    replaced_by = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="predecessor",
    )
    confirmation_nonce_digest = models.BinaryField(
        max_length=32,
        null=True,
        blank=True,
        editable=False,
    )
    confirmation_expires_at = models.DateTimeField(null=True, blank=True)
    confirmation_consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "-created_at"], name="auth_ref_session_created_idx"),
            models.Index(fields=["expires_at"], name="auth_ref_expires_idx"),
            models.Index(fields=["confirmation_expires_at"], name="auth_ref_confirm_exp_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["session"],
                condition=models.Q(used_at__isnull=True, revoked_at__isnull=True),
                name="auth_ref_one_live_per_session",
            ),
            models.UniqueConstraint(
                fields=["session"],
                condition=models.Q(confirmation_nonce_digest__isnull=False),
                name="auth_ref_one_confirmation_per_session",
            ),
            models.CheckConstraint(
                condition=models.Q(replaced_by__isnull=True) | models.Q(used_at__isnull=False),
                name="auth_ref_successor_spent",
            ),
            models.CheckConstraint(
                condition=~models.Q(uuid=models.F("replaced_by")),
                name="auth_ref_successor_not_self",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        confirmation_nonce_digest__isnull=True,
                        confirmation_expires_at__isnull=True,
                        confirmation_consumed_at__isnull=True,
                    )
                    | models.Q(
                        confirmation_nonce_digest__isnull=False,
                        confirmation_expires_at__isnull=False,
                        used_at__isnull=False,
                        replaced_by__isnull=False,
                    )
                ),
                name="auth_ref_confirmation_state",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.secret_digest is None or len(bytes(self.secret_digest)) != 32:
            errors["secret_digest"] = "Digest must be exactly 32 bytes."
        if self.confirmation_nonce_digest is not None and len(bytes(self.confirmation_nonce_digest)) != 32:
            errors["confirmation_nonce_digest"] = "Digest must be exactly 32 bytes."
        if self.replaced_by_id is not None and self.replaced_by_id != self.uuid:
            replacement_session_id = (
                type(self).objects.filter(uuid=self.replaced_by_id).values_list("session_id", flat=True).first()
            )
            if replacement_session_id is not None and replacement_session_id != self.session_id:
                errors["replaced_by"] = "Replacement must belong to the same session."
        if errors:
            raise ValidationError(errors)

    @property
    def is_spent(self):
        return self.used_at is not None

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    def is_expired(self, at=None):
        return self.expires_at <= (at or timezone.now())

    def matches_secret(self, secret, key):
        return refresh_secret_matches(self.secret_digest, self.uuid, secret, key)
