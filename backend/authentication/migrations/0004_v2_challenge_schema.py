import uuid

import django.db.models.deletion
import django.db.models.functions.text
import django.db.models.lookups
from django.conf import settings
from django.db import migrations, models

import authentication.security.v2_email


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0003_customuser_v2_email_constraints"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuthenticationChallenge",
            fields=[
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "purpose",
                    models.CharField(
                        choices=[
                            ("signup", "Signup"),
                            ("email_change", "Email change"),
                            ("password_reset", "Password reset"),
                        ],
                        editable=False,
                        max_length=16,
                    ),
                ),
                (
                    "transport",
                    models.CharField(
                        choices=[("browser", "Browser"), ("native", "Native")], editable=False, max_length=8
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("consumed", "Consumed"),
                            ("exhausted", "Exhausted"),
                            ("expired", "Expired"),
                            ("superseded", "Superseded"),
                            ("invalidated", "Invalidated"),
                        ],
                        default="open",
                        editable=False,
                        max_length=16,
                    ),
                ),
                ("pending_context_key_id", models.CharField(blank=True, editable=False, max_length=64, null=True)),
                ("pending_context_digest", models.BinaryField(blank=True, max_length=32, null=True)),
                ("target_email", models.EmailField(blank=True, editable=False, max_length=254, null=True)),
                ("otp_failure_count", models.PositiveSmallIntegerField(default=0, editable=False)),
                ("created_at", models.DateTimeField(editable=False)),
                ("expires_at", models.DateTimeField(editable=False)),
                ("resolved_at", models.DateTimeField(blank=True, editable=False, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="authentication_challenges",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "authentication_challenge",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AuthenticationChallengeDelivery",
            fields=[
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "purpose",
                    models.CharField(
                        choices=[
                            ("signup", "Signup"),
                            ("email_change", "Email change"),
                            ("password_reset", "Password reset"),
                        ],
                        editable=False,
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("reserved", "Reserved"),
                            ("sending", "Sending"),
                            ("ambiguous", "Ambiguous"),
                            ("active", "Active"),
                            ("rejected", "Rejected"),
                            ("abandoned", "Abandoned"),
                            ("suppressed", "Suppressed"),
                            ("superseded", "Superseded"),
                            ("consumed", "Consumed"),
                            ("exhausted", "Exhausted"),
                            ("expired", "Expired"),
                            ("invalidated", "Invalidated"),
                        ],
                        default="reserved",
                        editable=False,
                        max_length=16,
                    ),
                ),
                ("rate_key_id", models.CharField(editable=False, max_length=64)),
                ("destination_rate_digest", models.BinaryField(blank=True, max_length=32, null=True)),
                ("ip_rate_digest", models.BinaryField(max_length=32)),
                ("proof_key_id", models.CharField(blank=True, editable=False, max_length=64, null=True)),
                ("proof_digest", models.BinaryField(blank=True, max_length=32, null=True)),
                ("reserved_at", models.DateTimeField(editable=False)),
                ("lease_expires_at", models.DateTimeField(editable=False)),
                ("sending_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("accepted_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("proof_expires_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, editable=False, null=True)),
                (
                    "challenge",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="deliveries",
                        to="authentication.authenticationchallenge",
                    ),
                ),
            ],
            options={
                "db_table": "authentication_challenge_delivery",
                "ordering": ["-reserved_at"],
            },
        ),
        migrations.AddIndex(
            model_name="authenticationchallenge",
            index=models.Index(fields=["user", "purpose", "status", "expires_at"], name="auth_chal_user_state_idx"),
        ),
        migrations.AddIndex(
            model_name="authenticationchallenge",
            index=models.Index(fields=["status", "expires_at"], name="auth_chal_expiry_idx"),
        ),
        migrations.AddIndex(
            model_name="authenticationchallenge",
            index=models.Index(fields=["pending_context_key_id", "status", "created_at"], name="auth_chal_ctx_key_idx"),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(("purpose__in", ["signup", "email_change", "password_reset"])),
                name="auth_chal_purpose_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(("transport__in", ["browser", "native"])), name="auth_chal_transport_valid"
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("status__in", ["open", "consumed", "exhausted", "expired", "superseded", "invalidated"])
                ),
                name="auth_chal_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("pending_context_digest__isnull", False),
                        ("pending_context_key_id__isnull", False),
                        ("purpose__in", ["signup", "email_change"]),
                        models.Q(("pending_context_key_id", ""), _negated=True),
                    ),
                    models.Q(
                        ("pending_context_digest__isnull", True),
                        ("pending_context_key_id__isnull", True),
                        ("purpose", "password_reset"),
                    ),
                    _connector="OR",
                ),
                name="auth_chal_context_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("pending_context_digest__isnull", True),
                    django.db.models.lookups.Exact(
                        django.db.models.functions.text.Length("pending_context_digest"), 32
                    ),
                    _connector="OR",
                ),
                name="auth_chal_context_len",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("pending_context_key_id__isnull", True),
                    ("pending_context_key_id__regex", "\\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\\Z"),
                    _connector="OR",
                ),
                name="auth_chal_context_key",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("purpose", "email_change"), ("status", "open"), ("target_email__isnull", False)),
                    models.Q(
                        models.Q(("purpose", "email_change"), ("status", "open"), _negated=True),
                        ("target_email__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="auth_chal_target_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("target_email__isnull", True),
                    authentication.security.v2_email.V2EmailIsPrintableASCII(models.F("target_email")),
                    _connector="OR",
                ),
                name="auth_chal_target_ascii",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("target_email__isnull", True),
                    ("target_email", authentication.security.v2_email.V2EmailDestinationKey(models.F("target_email"))),
                    _connector="OR",
                ),
                name="auth_chal_target_canon",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(("otp_failure_count__gte", 0), ("otp_failure_count__lte", 5)),
                name="auth_chal_failure_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("purpose", "password_reset"), _negated=True), ("otp_failure_count", 0), _connector="OR"
                ),
                name="auth_chal_reset_no_failures",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("otp_failure_count", 5), ("purpose__in", ["signup", "email_change"]), ("status", "exhausted")
                    ),
                    models.Q(models.Q(("status", "exhausted"), _negated=True), ("otp_failure_count__lt", 5)),
                    _connector="OR",
                ),
                name="auth_chal_exhausted_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status", "superseded"), _negated=True), ("purpose", "email_change"), _connector="OR"
                ),
                name="auth_chal_supersede_purpose",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("resolved_at__isnull", True), ("status", "open")),
                    models.Q(models.Q(("status", "open"), _negated=True), ("resolved_at__isnull", False)),
                    _connector="OR",
                ),
                name="auth_chal_resolved_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(("expires_at__gt", models.F("created_at"))), name="auth_chal_expiry_order"
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("resolved_at__isnull", True), ("resolved_at__gte", models.F("created_at")), _connector="OR"
                ),
                name="auth_chal_resolved_order",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallenge",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "open")), fields=("user", "purpose"), name="auth_chal_open_user_uniq"
            ),
        ),
        migrations.AddIndex(
            model_name="authenticationchallengedelivery",
            index=models.Index(fields=["challenge", "status"], name="auth_del_chal_state_idx"),
        ),
        migrations.AddIndex(
            model_name="authenticationchallengedelivery",
            index=models.Index(fields=["status", "lease_expires_at"], name="auth_del_lease_idx"),
        ),
        migrations.AddIndex(
            model_name="authenticationchallengedelivery",
            index=models.Index(fields=["status", "reserved_at"], name="auth_del_cleanup_idx"),
        ),
        migrations.AddIndex(
            model_name="authenticationchallengedelivery",
            index=models.Index(
                fields=["rate_key_id", "destination_rate_digest", "reserved_at"], name="auth_del_dest_rate_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="authenticationchallengedelivery",
            index=models.Index(
                condition=models.Q(("purpose", "password_reset")),
                fields=["rate_key_id", "destination_rate_digest", "reserved_at"],
                name="auth_del_reset_rate_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="authenticationchallengedelivery",
            index=models.Index(fields=["rate_key_id", "ip_rate_digest", "reserved_at"], name="auth_del_ip_rate_idx"),
        ),
        migrations.AddIndex(
            model_name="authenticationchallengedelivery",
            index=models.Index(fields=["proof_key_id", "status", "reserved_at"], name="auth_del_proof_key_idx"),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(("purpose__in", ["signup", "email_change", "password_reset"])),
                name="auth_del_purpose_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "status__in",
                        [
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
                        ],
                    )
                ),
                name="auth_del_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(("rate_key_id__regex", "\\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\\Z")),
                name="auth_del_rate_key_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=django.db.models.lookups.Exact(django.db.models.functions.text.Length("ip_rate_digest"), 32),
                name="auth_del_ip_digest_len",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("destination_rate_digest__isnull", True),
                    django.db.models.lookups.Exact(
                        django.db.models.functions.text.Length("destination_rate_digest"), 32
                    ),
                    _connector="OR",
                ),
                name="auth_del_dest_digest_len",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("destination_rate_digest__isnull", False),
                    models.Q(("purpose__in", ["signup", "email_change"]), ("status", "suppressed")),
                    _connector="OR",
                ),
                name="auth_del_dest_digest_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("proof_digest__isnull", True),
                    django.db.models.lookups.Exact(django.db.models.functions.text.Length("proof_digest"), 32),
                    _connector="OR",
                ),
                name="auth_del_proof_digest_len",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("proof_key_id__isnull", True),
                    ("proof_key_id__regex", "\\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\\Z"),
                    _connector="OR",
                ),
                name="auth_del_proof_key_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("accepted_at__isnull", True),
                        ("proof_digest__isnull", True),
                        ("proof_expires_at__isnull", True),
                        ("proof_key_id__isnull", True),
                        ("sending_at__isnull", True),
                        ("status__in", ["reserved", "suppressed", "abandoned", "expired", "invalidated"]),
                    ),
                    models.Q(
                        ("accepted_at__isnull", True),
                        ("proof_digest__isnull", False),
                        ("proof_expires_at__isnull", True),
                        ("proof_key_id__isnull", False),
                        ("sending_at__isnull", False),
                        ("status__in", ["sending", "ambiguous", "rejected", "abandoned", "expired", "invalidated"]),
                        models.Q(("proof_key_id", ""), _negated=True),
                    ),
                    models.Q(
                        ("accepted_at__isnull", False),
                        ("proof_digest__isnull", False),
                        ("proof_expires_at__isnull", False),
                        ("proof_key_id__isnull", False),
                        ("sending_at__isnull", False),
                        ("status__in", ["active", "superseded", "consumed", "exhausted", "expired", "invalidated"]),
                        models.Q(("proof_key_id", ""), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="auth_del_proof_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("resolved_at__isnull", True), ("status__in", ["reserved", "sending", "ambiguous", "active"])
                    ),
                    models.Q(
                        ("resolved_at__isnull", False),
                        (
                            "status__in",
                            [
                                "rejected",
                                "abandoned",
                                "suppressed",
                                "superseded",
                                "consumed",
                                "exhausted",
                                "expired",
                                "invalidated",
                            ],
                        ),
                    ),
                    _connector="OR",
                ),
                name="auth_del_resolved_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status", "exhausted"), _negated=True),
                    ("purpose__in", ["signup", "email_change"]),
                    _connector="OR",
                ),
                name="auth_del_exhausted_purpose",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("challenge__isnull", False),
                    (
                        "status__in",
                        [
                            "rejected",
                            "abandoned",
                            "suppressed",
                            "superseded",
                            "consumed",
                            "exhausted",
                            "expired",
                            "invalidated",
                        ],
                    ),
                    _connector="OR",
                ),
                name="auth_del_challenge_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(("lease_expires_at__gt", models.F("reserved_at"))), name="auth_del_lease_order"
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("sending_at__isnull", True),
                    models.Q(
                        ("sending_at__gte", models.F("reserved_at")), ("sending_at__lt", models.F("lease_expires_at"))
                    ),
                    _connector="OR",
                ),
                name="auth_del_sending_order",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("accepted_at__isnull", True),
                    models.Q(
                        ("accepted_at__gte", models.F("sending_at")), ("accepted_at__lt", models.F("lease_expires_at"))
                    ),
                    _connector="OR",
                ),
                name="auth_del_accepted_order",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("proof_expires_at__isnull", True),
                    ("proof_expires_at__gt", models.F("accepted_at")),
                    _connector="OR",
                ),
                name="auth_del_proof_expiry_order",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("resolved_at__isnull", True), ("resolved_at__gte", models.F("reserved_at")), _connector="OR"
                ),
                name="auth_del_resolved_order",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("sending_at__isnull", True),
                    ("resolved_at__isnull", True),
                    ("resolved_at__gte", models.F("sending_at")),
                    _connector="OR",
                ),
                name="auth_del_resolved_send_order",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("accepted_at__isnull", True),
                    ("resolved_at__isnull", True),
                    ("resolved_at__gte", models.F("accepted_at")),
                    _connector="OR",
                ),
                name="auth_del_resolved_accept_order",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "active")), fields=("challenge",), name="auth_del_one_active"
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status__in", ["reserved", "sending", "ambiguous"])),
                fields=("challenge",),
                name="auth_del_one_inflight",
            ),
        ),
    ]
