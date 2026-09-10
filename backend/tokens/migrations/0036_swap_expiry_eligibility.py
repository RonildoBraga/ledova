from django.db import migrations, models


def preserve_expiry_eligibility(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("""
            CREATE FUNCTION swaps_preserve_expiry_eligibility() RETURNS trigger AS $$
            BEGIN
                IF NEW.expiry_release_eligible IS DISTINCT FROM OLD.expiry_release_eligible THEN
                    RAISE EXCEPTION 'Swap expiry eligibility is fixed at creation'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER swaps_preserve_expiry_eligibility
            BEFORE UPDATE ON tokens_swaporder
            FOR EACH ROW EXECUTE FUNCTION swaps_preserve_expiry_eligibility();
            """)


def unprotect_expiry_eligibility(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "DROP TRIGGER swaps_preserve_expiry_eligibility ON tokens_swaporder;"
            "DROP FUNCTION swaps_preserve_expiry_eligibility();"
        )


class Migration(migrations.Migration):

    dependencies = [("tokens", "0035_trading_state_invariants")]

    operations = [
        migrations.AddField(
            model_name="swaporder",
            name="expiry_release_eligible",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.RunPython(preserve_expiry_eligibility, unprotect_expiry_eligibility),
    ]
