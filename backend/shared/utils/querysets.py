from django.db.models import QuerySet


def sample_evenly(rows, max_points):
    """At most `max_points` rows spread evenly over a queryset or sequence in its current order.

    A missing, non-numeric or non-positive `max_points` returns the rows untouched.
    """
    try:
        max_points = int(max_points)
    except (TypeError, ValueError):
        return rows
    if max_points <= 0:
        return rows

    is_queryset = isinstance(rows, QuerySet)
    keys = list(rows.values_list("pk", flat=True)) if is_queryset else rows
    if len(keys) <= max_points:
        return rows

    step = (len(keys) - 1) / (max_points - 1) if max_points > 1 else 0
    picked = [keys[round(i * step)] for i in range(max_points)]
    return rows.filter(pk__in=picked) if is_queryset else picked
