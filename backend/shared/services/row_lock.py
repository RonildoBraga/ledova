from shared.db import atomic


def act_under_row_lock(queryset, pk, act):
    with atomic():
        row = queryset.select_for_update().get(pk=pk)
        value, refusal = act(row)

    if refusal is not None:
        raise refusal

    return value
