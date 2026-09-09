from django.db import migrations, models

GUARD = """
CREATE FUNCTION blockchain_guard_signer_admission() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.admission_generation < OLD.admission_generation
       OR (NEW.admission_state IS DISTINCT FROM OLD.admission_state
           AND NEW.admission_generation <= OLD.admission_generation) THEN
        RAISE EXCEPTION 'Outgoing signer admission generations cannot be reused or rewound';
    END IF;
    RETURN NEW;
END;
$$
"""


def install_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(GUARD)
        cursor.execute(
            "CREATE TRIGGER blockchain_signingaccount_admission BEFORE UPDATE ON blockchain_signingaccount "
            "FOR EACH ROW EXECUTE FUNCTION blockchain_guard_signer_admission()"
        )


def remove_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER blockchain_signingaccount_admission ON blockchain_signingaccount")
        cursor.execute("DROP FUNCTION blockchain_guard_signer_admission()")


class Migration(migrations.Migration):
    dependencies = [("blockchain", "0005_legacy_outgoing_inventory")]

    operations = [
        migrations.AddField(
            model_name="signingaccount",
            name="admission_state",
            field=models.CharField(
                choices=[("closed", "Closed"), ("admitted", "Admitted")],
                default="closed",
                editable=False,
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="signingaccount",
            name="admission_generation",
            field=models.PositiveBigIntegerField(default=0, editable=False),
        ),
        migrations.AddConstraint(
            model_name="signingaccount",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(admission_state="closed")
                    | models.Q(
                        admission_state="admitted",
                        admission_generation__gt=0,
                        admission_generation__lt=9223372036854775807,
                    )
                ),
                name="outgoing_signer_admission",
            ),
        ),
        migrations.RunPython(install_guard, remove_guard),
    ]
