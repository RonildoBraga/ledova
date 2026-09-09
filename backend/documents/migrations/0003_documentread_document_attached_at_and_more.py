import uuid

import django.db.models.deletion
from django.db import migrations, models


def seed_operations_group(apps, schema_editor):
    using = schema_editor.connection.alias
    group, _ = apps.get_model("auth", "Group").objects.using(using).get_or_create(name="Document operations")
    for label, model in (
        ("documents", "document"),
        ("documents", "documentextraction"),
        ("users", "investorclassification"),
    ):
        content_type, _ = (
            apps.get_model("contenttypes", "ContentType")
            .objects.using(using)
            .get_or_create(app_label=label, model=model)
        )
        permission, _ = (
            apps.get_model("auth", "Permission")
            .objects.using(using)
            .get_or_create(content_type=content_type, codename=f"view_{model}", defaults={"name": f"Can view {model}"})
        )
        group.permissions.through.objects.using(using).get_or_create(group_id=group.pk, permission_id=permission.pk)


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0002_document_private_storage"),
        ("users", "0018_investor_classification"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentRead",
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
                ("actor_id", models.PositiveBigIntegerField()),
                ("document_uuid", models.UUIDField(db_index=True)),
                ("classification_uuid", models.UUIDField(blank=True, null=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[("document", "Document"), ("file", "File"), ("extraction", "Extraction")],
                        max_length=16,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="document",
            name="attached_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="document",
            name="classification",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="supporting_documents",
                to="users.investorclassification",
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="purged_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(seed_operations_group, migrations.RunPython.noop),
    ]
