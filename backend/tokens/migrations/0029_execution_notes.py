from django.db import migrations, models

NOTES = "What each execution attempt did, in order. Written by the system; review_notes is the person's"
MACHINE_PREFIXES = ("Execution refused: ", "Execution failed: ")
REQUESTS = ("ShareIssuanceRequest", "CapitalIncreaseRequest")


def move_what_the_system_wrote(apps, schema_editor):
    alias = schema_editor.connection.alias
    for name in REQUESTS:
        model = apps.get_model("tokens", name)
        moved = []
        for request in model._base_manager.using(alias).exclude(review_notes=""):
            if request.review_notes.startswith(MACHINE_PREFIXES):
                request.execution_notes = request.review_notes
                request.review_notes = ""
                moved.append(request)
        model._base_manager.using(alias).bulk_update(moved, ["review_notes", "execution_notes"])


def put_it_back_where_it_was(apps, schema_editor):
    alias = schema_editor.connection.alias
    for name in REQUESTS:
        model = apps.get_model("tokens", name)
        restored = []
        for request in model._base_manager.using(alias).filter(review_notes="").exclude(execution_notes=""):
            if request.execution_notes.startswith(MACHINE_PREFIXES):
                request.review_notes = request.execution_notes
                request.execution_notes = ""
                restored.append(request)
        model._base_manager.using(alias).bulk_update(restored, ["review_notes", "execution_notes"])


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0025_a_token_cannot_change_company"),
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
        migrations.RunPython(move_what_the_system_wrote, put_it_back_where_it_was),
    ]
