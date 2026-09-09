import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from shared.db.policy_sql import install

DERIVE_AND_REFUSE = """
CREATE OR REPLACE FUNCTION {function}() RETURNS trigger AS $derive$
DECLARE
    parent_owner_id {grandparent_table}.{grandparent_owner}%TYPE;
BEGIN
    SELECT grandparent.{grandparent_owner} INTO parent_owner_id
    FROM {parent_table} AS parent
    JOIN {grandparent_table} AS grandparent ON grandparent.{grandparent_pk} = parent.{parent_company}
    WHERE parent.{parent_pk} = NEW.{parent_fk};

    IF parent_owner_id IS NULL THEN
        RAISE EXCEPTION '{table}.{column} cannot be derived: {parent_table} % has no owner', NEW.{parent_fk};
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF NEW.{parent_fk} IS DISTINCT FROM OLD.{parent_fk}
           AND parent_owner_id IS DISTINCT FROM OLD.{column} THEN
            RAISE EXCEPTION '{table} cannot move this row to another owner, from % to %',
                OLD.{column}, parent_owner_id;
        END IF;

        IF NEW.{column} IS NULL OR NEW.{column} IS NOT DISTINCT FROM OLD.{column} THEN
            NEW.{column} := parent_owner_id;
        ELSIF NEW.{column} <> parent_owner_id THEN
            RAISE EXCEPTION '{table}.{column} cannot be moved to %: {parent_table} % names %',
                NEW.{column}, NEW.{parent_fk}, parent_owner_id;
        END IF;
    ELSE
        IF NEW.{column} IS NULL THEN
            NEW.{column} := parent_owner_id;
        ELSIF NEW.{column} <> parent_owner_id THEN
            RAISE EXCEPTION '{table}.{column} % does not match the owner of {parent_table} %',
                NEW.{column}, parent_owner_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$derive$ LANGUAGE plpgsql;
"""

TRIGGER = """
CREATE TRIGGER {trigger}
BEFORE INSERT OR UPDATE ON {table}
FOR EACH ROW EXECUTE FUNCTION {function}();
"""

DROP_TRIGGER = "DROP TRIGGER IF EXISTS {trigger} ON {table};"

DROP_FUNCTION = "DROP FUNCTION IF EXISTS {function}();"


def _names(apps):
    model = apps.get_model("tokens", "FormerHolder")
    parent = apps.get_model("tokens", "ShareToken")
    grandparent = apps.get_model("companies", "Company")
    table = model._meta.db_table
    column = model._meta.get_field("owner").column
    return {
        "table": table,
        "column": column,
        "parent_table": parent._meta.db_table,
        "parent_pk": parent._meta.pk.column,
        "parent_fk": model._meta.get_field("token").column,
        "parent_company": parent._meta.get_field("company").column,
        "grandparent_table": grandparent._meta.db_table,
        "grandparent_pk": grandparent._meta.pk.column,
        "grandparent_owner": grandparent._meta.get_field("owner").column,
        "function": f"{table}_{column}_is_derived",
        "trigger": f"{table}_{column}_derive",
    }


def install_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    names = _names(apps)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(DERIVE_AND_REFUSE.format(**names))
        cursor.execute(DROP_TRIGGER.format(**names))
        cursor.execute(TRIGGER.format(**names))


def install_policies(apps, schema_editor):
    install(schema_editor)


def policies_go_with_the_table(apps, schema_editor):
    return


def drop_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    names = _names(apps)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(DROP_TRIGGER.format(**names))
        cursor.execute(DROP_FUNCTION.format(**names))


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0031_share_tokens_have_zero_decimals"),
        ("companies", "0007_alter_company_abn_alter_company_acn"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FormerHolder",
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
                ("wallet_address", models.CharField(db_index=True, max_length=42)),
                ("ceased_on", models.DateField(db_index=True)),
                ("ceased_at_block", models.BigIntegerField()),
                ("shares_at_cessation", models.BigIntegerField()),
                ("name", models.CharField(blank=True, max_length=255)),
                ("residential_address", models.TextField(blank=True)),
                (
                    "identity_source",
                    models.CharField(
                        choices=[
                            ("profile", "Current profile"),
                            ("stamped", "Stamped at the time"),
                            ("recorded", "Name recorded at allotment, identity never resolved"),
                            ("treasury_label", "Whitelist entry label, no profile exists"),
                            ("unresolvable", "Not resolvable, two wallets share this address"),
                            ("none", "Not identified"),
                            ("unknown", "Never identified while it held shares"),
                        ],
                        default="unknown",
                        max_length=20,
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        help_text="Owner, derived from token.company.owner and held directly so a row-level security policy can read it without joining companies",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "token",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="former_holders",
                        to="tokens.sharetoken",
                    ),
                ),
            ],
            options={
                "verbose_name": "Former holder",
                "verbose_name_plural": "Former holders",
                "db_table": "tokens_formerholder",
                "ordering": ["-ceased_on", "wallet_address"],
                "indexes": [models.Index(fields=["token", "-ceased_on"], name="tokens_form_token_i_7339eb_idx")],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("token", "wallet_address", "ceased_at_block"), name="one_cessation_per_wallet_per_block"
                    )
                ],
            },
        ),
        migrations.RunPython(install_trigger, drop_trigger),
        migrations.RunPython(install_policies, policies_go_with_the_table),
    ]
