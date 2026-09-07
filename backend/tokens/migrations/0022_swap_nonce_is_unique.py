from django.db import migrations, models
from django.db.models import Count


def refuse_duplicate_nonces(apps, schema_editor):
    SwapOrder = apps.get_model("tokens", "SwapOrder")
    shared = list(
        SwapOrder.objects.values("nonce")
        .annotate(rows=Count("uuid"))
        .filter(rows__gt=1)
        .order_by("nonce")
        .values_list("nonce", flat=True)[:20]
    )
    if not shared:
        return

    collisions = []
    for nonce in shared:
        swaps = SwapOrder.objects.filter(nonce=nonce).order_by("created_at").values_list("uuid", flat=True)
        collisions.append(f"{nonce}: " + ", ".join(str(uuid) for uuid in swaps))

    raise RuntimeError(
        "Swap nonces are meant to be unique and these are not, so the constraint cannot be added:\n  "
        + "\n  ".join(collisions)
        + "\nA nonce is part of what each party signed, so do not rewrite one. Decide which swap is real."
    )


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0021_modification_log_names_its_challenge"),
    ]

    operations = [
        migrations.RunPython(refuse_duplicate_nonces, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="swaporder",
            constraint=models.UniqueConstraint(fields=("nonce",), name="unique_swap_nonce"),
        ),
    ]
