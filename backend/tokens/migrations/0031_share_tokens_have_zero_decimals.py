from django.core.validators import MaxValueValidator
from django.db import migrations, models


def refuse_nonzero_share_decimals(apps, schema_editor):
    token = apps.get_model("tokens", "ShareToken")
    rows = list(
        token._base_manager.using(schema_editor.connection.alias).exclude(decimals=0).values_list("uuid", "decimals")
    )
    if rows:
        details = ", ".join(f"{uuid} (decimals={decimals})" for uuid, decimals in rows)
        raise RuntimeError(
            f"Share tokens use whole units, but these records have nonzero decimals: {details}. "
            "Review and correct these records before applying this migration; no values have been changed."
        )


class Migration(migrations.Migration):

    dependencies = [("tokens", "0029_execution_notes")]

    operations = [
        migrations.RunPython(refuse_nonzero_share_decimals, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="sharetoken",
            name="decimals",
            field=models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(0)]),
        ),
        migrations.AddConstraint(
            model_name="sharetoken",
            constraint=models.CheckConstraint(condition=models.Q(decimals=0), name="share_token_whole_units"),
        ),
    ]
