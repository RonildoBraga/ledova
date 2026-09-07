from django.db import transaction


def act_under_row_lock(queryset, pk, act):
    with transaction.atomic():
        row = queryset.select_for_update().get(pk=pk)
        value, refusal = act(row)

    if refusal is not None:
        raise refusal

    return value
