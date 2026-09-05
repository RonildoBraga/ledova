import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import users.models.investor_classification


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0004_company_additional_info_response"),
        ("users", "0017_delete_waitlist"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InvestorClassification",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier (primary key)",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("product_value", "Product value of at least AUD 500,000 (s708(8)(a))"),
                            ("accountant_certificate", "Qualified accountant's certificate (s708(8)(c))"),
                            ("professional_investor", "Professional investor (s708(11) / s761G(7)(d))"),
                            ("associated_person", "Person associated with the issuer (s708(12))"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("submitted", "Submitted"),
                            ("verified", "Verified"),
                            ("rejected", "Rejected"),
                            ("revoked", "Revoked"),
                        ],
                        default="submitted",
                        max_length=20,
                    ),
                ),
                ("declaration_accepted", models.BooleanField(default=False)),
                ("declaration_text", models.TextField(blank=True)),
                ("declared_basis", models.TextField(blank=True)),
                (
                    "evidence_file",
                    models.FileField(
                        blank=True,
                        max_length=255,
                        null=True,
                        upload_to=users.models.investor_classification.investor_evidence_path,
                    ),
                ),
                ("evidence_file_size", models.PositiveIntegerField(blank=True, null=True)),
                ("evidence_mime_type", models.CharField(blank=True, max_length=100)),
                ("certificate_issued_at", models.DateField(blank=True, null=True)),
                ("certifier_name", models.CharField(blank=True, max_length=255)),
                (
                    "certifier_body",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("ca_anz", "Chartered Accountants Australia and New Zealand"),
                            ("cpa_australia", "CPA Australia"),
                            ("ipa", "Institute of Public Accountants"),
                        ],
                        max_length=20,
                    ),
                ),
                ("certifier_membership_number", models.CharField(blank=True, max_length=50)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("review_notes", models.TextField(blank=True)),
                ("rejection_reason", models.TextField(blank=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                (
                    "company",
                    models.ForeignKey(
                        blank=True,
                        help_text="Set only for an associated person; empty means the claim applies to every offering.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="investor_classifications",
                        to="companies.company",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Staff member who reviewed the claim",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_investor_classifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="investor_classifications",
                        to="users.useraccount",
                    ),
                ),
            ],
            options={
                "verbose_name": "Investor Classification",
                "verbose_name_plural": "Investor Classifications",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["user_account", "status"], name="users_inves_user_ac_5d17c5_idx"),
                    models.Index(fields=["status"], name="users_inves_status_b9facf_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("status", "submitted")),
                        fields=("user_account",),
                        name="investor_classification_one_open_submission",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("category", "associated_person"), ("company__isnull", False)),
                            models.Q(
                                models.Q(("category", "associated_person"), _negated=True), ("company__isnull", True)
                            ),
                            _connector="OR",
                        ),
                        name="investor_classification_associated_person_names_the_issuer",
                        violation_error_message="An associated person claim must name the issuer it is scoped to, and no other category may name one.",
                    ),
                ],
            },
        ),
    ]
