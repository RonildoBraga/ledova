from django.db import migrations, models

NOTES = "What each execution attempt did, in order. Written by the system; review_notes is the person's"
LEGACY_CONTEXT = (
    "Legacy review notes are preserved verbatim and may include earlier execution messages. "
    "They describe the past; the request status records the current outcome."
)
REVIEW_NOTES = "Reviewer notes; older entries may also contain historical execution messages"
REQUESTS = ("ShareIssuanceRequest", "CapitalIncreaseRequest")


def retain_legacy_history(apps, schema_editor):
    alias = schema_editor.connection.alias
    for name in REQUESTS:
        model = apps.get_model("tokens", name)
        model._base_manager.using(alias).exclude(review_notes="").filter(execution_notes="").update(
            execution_notes=LEGACY_CONTEXT
        )


def remove_legacy_context(apps, schema_editor):
    alias = schema_editor.connection.alias
    for name in REQUESTS:
        model = apps.get_model("tokens", name)
        model._base_manager.using(alias).filter(execution_notes=LEGACY_CONTEXT).update(execution_notes="")


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0030_superseded_capital_increase"),
    ]

    operations = [
        migrations.AddField(
            model_name="capitalincreaserequest",
            name="execution_notes",
            field=models.TextField(blank=True, help_text=NOTES),
        ),
        migrations.AddField(
            model_name="shareissuancerequest",
            name="execution_notes",
            field=models.TextField(blank=True, help_text=NOTES),
        ),
        migrations.AlterField(
            model_name="capitalincreaserequest",
            name="review_notes",
            field=models.TextField(blank=True, help_text=REVIEW_NOTES),
        ),
        migrations.AlterField(
            model_name="shareissuancerequest",
            name="review_notes",
            field=models.TextField(blank=True, help_text=REVIEW_NOTES),
        ),
        migrations.RunPython(retain_legacy_history, remove_legacy_context),
    ]
