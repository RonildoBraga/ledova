from django.conf import settings
from django.db import migrations, models
from django.db.models import Count

IN_FLIGHT = ("submitted", "under_review", "approved", "executing")


def refuse_a_token_that_already_has_two(apps, schema_editor):
    model = apps.get_model("tokens", "CapitalIncreaseRequest")
    alias = schema_editor.connection.alias
    crowded = (
        model._base_manager.using(alias)
        .filter(status__in=IN_FLIGHT)
        .values("token_id")
        .annotate(in_flight=Count("uuid"))
        .filter(in_flight__gt=1)
        .order_by("token_id")
    )
    offenders = [row["token_id"] for row in crowded]
    if not offenders:
        return

    crowding = (
        model._base_manager.using(alias)
        .filter(status__in=IN_FLIGHT, token_id__in=offenders)
        .select_related("token")
        .order_by("token_id", "created_at")
    )
    by_class = {}
    for request in crowding:
        heading = f"{request.token.symbol} ({request.token_id})"
        by_class.setdefault(heading, []).append(f"{request.uuid} ({request.status})")
    named = "; ".join(f"{heading}: {', '.join(rows)}" for heading, rows in by_class.items())

    raise RuntimeError(
        "This migration allows one capital increase in flight per share class, and these already have more "
        f"than one: {named}. Which of them should proceed is a decision for an operator, not for a migration, "
        "so nothing has been changed. Resolve each to a single in-flight request and run this again."
    )


def nothing_to_undo(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0007_alter_company_abn_alter_company_acn"),
        ("tokens", "0025_a_token_cannot_change_company"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(refuse_a_token_that_already_has_two, nothing_to_undo),
        migrations.AddConstraint(
            model_name="capitalincreaserequest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status__in", IN_FLIGHT)),
                fields=("token",),
                name="one_capital_increase_in_flight_per_token",
            ),
        ),
    ]
