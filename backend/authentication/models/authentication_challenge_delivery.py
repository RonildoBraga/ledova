import uuid

from django.db import models
from django.db.models.functions import Length
from django.db.models.lookups import Exact


class AuthenticationChallengeDelivery(models.Model):
    class Purpose(models.TextChoices):
        SIGNUP = "signup", "Signup"
        EMAIL_CHANGE = "email_change", "Email change"
        PASSWORD_RESET = "password_reset", "Password reset"

    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        SENDING = "sending", "Sending"
        AMBIGUOUS = "ambiguous", "Ambiguous"
        ACTIVE = "active", "Active"
        REJECTED = "rejected", "Rejected"
        ABANDONED = "abandoned", "Abandoned"
        SUPPRESSED = "suppressed", "Suppressed"
        SUPERSEDED = "superseded", "Superseded"
        CONSUMED = "consumed", "Consumed"
        EXHAUSTED = "exhausted", "Exhausted"
        EXPIRED = "expired", "Expired"
        INVALIDATED = "invalidated", "Invalidated"

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    challenge = models.ForeignKey(
        "authentication.AuthenticationChallenge",
        on_delete=models.SET_NULL,
        related_name="deliveries",
        null=True,
        blank=True,
        editable=False,
    )
    purpose = models.CharField(max_length=16, choices=Purpose.choices, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RESERVED, editable=False)
    rate_key_id = models.CharField(max_length=64, editable=False)
    destination_rate_digest = models.BinaryField(max_length=32, null=True, blank=True, editable=False)
    ip_rate_digest = models.BinaryField(max_length=32, editable=False)
    proof_key_id = models.CharField(max_length=64, null=True, blank=True, editable=False)
    proof_digest = models.BinaryField(max_length=32, null=True, blank=True, editable=False)
    reserved_at = models.DateTimeField(editable=False)
    lease_expires_at = models.DateTimeField(editable=False)
    sending_at = models.DateTimeField(null=True, blank=True, editable=False)
    accepted_at = models.DateTimeField(null=True, blank=True, editable=False)
    proof_expires_at = models.DateTimeField(null=True, blank=True, editable=False)
    resolved_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "authentication_challenge_delivery"
        ordering = ["-reserved_at"]
        indexes = [
            models.Index(fields=["challenge", "status"], name="auth_del_chal_state_idx"),
            models.Index(fields=["status", "lease_expires_at"], name="auth_del_lease_idx"),
            models.Index(fields=["status", "reserved_at"], name="auth_del_cleanup_idx"),
            models.Index(
                fields=["rate_key_id", "destination_rate_digest", "reserved_at"],
                name="auth_del_dest_rate_idx",
            ),
            models.Index(
                fields=["rate_key_id", "destination_rate_digest", "reserved_at"],
                condition=models.Q(purpose="password_reset"),
                name="auth_del_reset_rate_idx",
            ),
            models.Index(
                fields=["rate_key_id", "ip_rate_digest", "reserved_at"],
                name="auth_del_ip_rate_idx",
            ),
            models.Index(
                fields=["proof_key_id", "status", "reserved_at"],
                name="auth_del_proof_key_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(purpose__in=["signup", "email_change", "password_reset"]),
                name="auth_del_purpose_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "reserved",
                        "sending",
                        "ambiguous",
                        "active",
                        "rejected",
                        "abandoned",
                        "suppressed",
                        "superseded",
                        "consumed",
                        "exhausted",
                        "expired",
                        "invalidated",
                    ]
                ),
                name="auth_del_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(rate_key_id__regex=r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z"),
                name="auth_del_rate_key_valid",
            ),
            models.CheckConstraint(
                condition=Exact(Length("ip_rate_digest"), 32),
                name="auth_del_ip_digest_len",
            ),
            models.CheckConstraint(
                condition=models.Q(destination_rate_digest__isnull=True) | Exact(Length("destination_rate_digest"), 32),
                name="auth_del_dest_digest_len",
            ),
            models.CheckConstraint(
                condition=models.Q(destination_rate_digest__isnull=False)
                | models.Q(
                    purpose__in=["signup", "email_change"],
                    status="suppressed",
                ),
                name="auth_del_dest_digest_state",
            ),
            models.CheckConstraint(
                condition=models.Q(proof_digest__isnull=True) | Exact(Length("proof_digest"), 32),
                name="auth_del_proof_digest_len",
            ),
            models.CheckConstraint(
                condition=models.Q(proof_key_id__isnull=True)
                | models.Q(proof_key_id__regex=r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z"),
                name="auth_del_proof_key_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=[
                            "reserved",
                            "suppressed",
                            "abandoned",
                            "superseded",
                            "expired",
                            "invalidated",
                        ],
                        proof_digest__isnull=True,
                        proof_key_id__isnull=True,
                        sending_at__isnull=True,
                        accepted_at__isnull=True,
                        proof_expires_at__isnull=True,
                    )
                    | (
                        models.Q(
                            status__in=[
                                "sending",
                                "ambiguous",
                                "rejected",
                                "abandoned",
                                "superseded",
                                "expired",
                                "invalidated",
                            ],
                            proof_digest__isnull=False,
                            proof_key_id__isnull=False,
                            sending_at__isnull=False,
                            accepted_at__isnull=True,
                            proof_expires_at__isnull=True,
                        )
                        & ~models.Q(proof_key_id="")
                    )
                    | (
                        models.Q(
                            status__in=["active", "superseded", "consumed", "exhausted", "expired", "invalidated"],
                            proof_digest__isnull=False,
                            proof_key_id__isnull=False,
                            sending_at__isnull=False,
                            accepted_at__isnull=False,
                            proof_expires_at__isnull=False,
                        )
                        & ~models.Q(proof_key_id="")
                    )
                ),
                name="auth_del_proof_state",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="superseded", accepted_at__isnull=True) | models.Q(purpose="email_change"),
                name="auth_del_supersede_purpose",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=["reserved", "sending", "ambiguous", "active"],
                        resolved_at__isnull=True,
                    )
                    | models.Q(
                        status__in=[
                            "rejected",
                            "abandoned",
                            "suppressed",
                            "superseded",
                            "consumed",
                            "exhausted",
                            "expired",
                            "invalidated",
                        ],
                        resolved_at__isnull=False,
                    )
                ),
                name="auth_del_resolved_state",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="exhausted") | models.Q(purpose__in=["signup", "email_change"]),
                name="auth_del_exhausted_purpose",
            ),
            models.CheckConstraint(
                condition=models.Q(challenge__isnull=False)
                | models.Q(
                    status__in=[
                        "rejected",
                        "abandoned",
                        "suppressed",
                        "superseded",
                        "consumed",
                        "exhausted",
                        "expired",
                        "invalidated",
                    ]
                ),
                name="auth_del_challenge_state",
            ),
            models.CheckConstraint(
                condition=models.Q(lease_expires_at__gt=models.F("reserved_at")),
                name="auth_del_lease_order",
            ),
            models.CheckConstraint(
                condition=models.Q(sending_at__isnull=True)
                | (
                    models.Q(sending_at__gte=models.F("reserved_at"))
                    & models.Q(sending_at__lt=models.F("lease_expires_at"))
                ),
                name="auth_del_sending_order",
            ),
            models.CheckConstraint(
                condition=models.Q(accepted_at__isnull=True)
                | (
                    models.Q(accepted_at__gte=models.F("sending_at"))
                    & models.Q(accepted_at__lt=models.F("lease_expires_at"))
                ),
                name="auth_del_accepted_order",
            ),
            models.CheckConstraint(
                condition=models.Q(proof_expires_at__isnull=True)
                | models.Q(proof_expires_at__gt=models.F("accepted_at")),
                name="auth_del_proof_expiry_order",
            ),
            models.CheckConstraint(
                condition=models.Q(resolved_at__isnull=True) | models.Q(resolved_at__gte=models.F("reserved_at")),
                name="auth_del_resolved_order",
            ),
            models.CheckConstraint(
                condition=models.Q(sending_at__isnull=True)
                | models.Q(resolved_at__isnull=True)
                | models.Q(resolved_at__gte=models.F("sending_at")),
                name="auth_del_resolved_send_order",
            ),
            models.CheckConstraint(
                condition=models.Q(accepted_at__isnull=True)
                | models.Q(resolved_at__isnull=True)
                | models.Q(resolved_at__gte=models.F("accepted_at")),
                name="auth_del_resolved_accept_order",
            ),
            models.UniqueConstraint(
                fields=["challenge"],
                condition=models.Q(status="active"),
                name="auth_del_one_active",
            ),
            models.UniqueConstraint(
                fields=["challenge"],
                condition=models.Q(status__in=["reserved", "sending", "ambiguous"]),
                name="auth_del_one_inflight",
            ),
        ]

    def __str__(self):
        return "AuthenticationChallengeDelivery(<redacted>)"

    def __repr__(self):
        return "AuthenticationChallengeDelivery(<redacted>)"
