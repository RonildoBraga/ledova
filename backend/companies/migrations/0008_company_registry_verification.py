import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

from shared.db.policy_sql import install_tables


def registry_policy(apps, schema_editor):
    install_tables(schema_editor, ["companies_companyregistrycheck"])


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0007_alter_company_abn_alter_company_acn"),
        ("shared", "0003_rls_roles_and_grants"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="board_resolution_reference",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="company",
            name="declarant_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="company",
            name="lifecycle_revision",
            field=models.PositiveBigIntegerField(default=0, editable=False),
        ),
        migrations.AddField(
            model_name="company",
            name="officeholder_attestation",
            field=models.JSONField(blank=True, default=dict, editable=False),
        ),
        migrations.AddField(
            model_name="company",
            name="officeholder_attested_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="company",
            name="officeholder_attested_by",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="registry_checked_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="company",
            name="registry_entity_name",
            field=models.CharField(blank=True, editable=False, max_length=255),
        ),
        migrations.AddField(
            model_name="company",
            name="registry_entity_status",
            field=models.CharField(blank=True, editable=False, max_length=32),
        ),
        migrations.AddField(
            model_name="company",
            name="registry_identity",
            field=models.JSONField(blank=True, default=dict, editable=False),
        ),
        migrations.AddField(
            model_name="company",
            name="registry_purpose",
            field=models.CharField(blank=True, editable=False, max_length=16),
        ),
        migrations.AddField(
            model_name="company",
            name="registry_reason",
            field=models.CharField(blank=True, editable=False, max_length=40),
        ),
        migrations.AddField(
            model_name="company",
            name="registry_revision",
            field=models.PositiveBigIntegerField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name="company",
            name="registry_status",
            field=models.CharField(
                choices=[("pending", "Pending"), ("passed", "Passed"), ("failed", "Failed")],
                default="pending",
                editable=False,
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="CompanyRegistryCheck",
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
                    "purpose",
                    models.CharField(
                        choices=[("review", "Start review"), ("retry", "Retry"), ("activation", "Activation")],
                        max_length=16,
                    ),
                ),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("completed_at", models.DateTimeField(null=True)),
                ("requested_name", models.CharField(max_length=255)),
                ("requested_acn", models.CharField(max_length=11)),
                ("requested_abn", models.CharField(blank=True, max_length=14)),
                ("identity", models.JSONField()),
                ("lifecycle_revision", models.PositiveBigIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("passed", "Passed"), ("failed", "Failed")],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("reason", models.CharField(blank=True, max_length=40)),
                ("registry_abn", models.CharField(blank=True, max_length=14)),
                ("registry_acn", models.CharField(blank=True, max_length=11)),
                ("entity_name", models.CharField(blank=True, max_length=255)),
                ("entity_type", models.CharField(blank=True, max_length=16)),
                ("entity_status", models.CharField(blank=True, max_length=32)),
                ("effective_from", models.DateField(null=True)),
                ("retrieved_at", models.CharField(blank=True, max_length=40)),
                ("register_updated_at", models.DateField(null=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="registry_checks",
                        to="companies.company",
                    ),
                ),
                (
                    "initiated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-started_at", "-uuid"],
            },
        ),
        migrations.AddField(
            model_name="company",
            name="registry_check",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="companies.companyregistrycheck",
            ),
        ),
        migrations.RunPython(registry_policy, migrations.RunPython.noop),
    ]
