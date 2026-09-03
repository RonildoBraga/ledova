def sample_evenly(queryset, max_points):
    """At most `max_points` rows spread evenly over the queryset in its current order.

    A missing, non-numeric or non-positive `max_points` returns the queryset untouched.
    """
    try:
        max_points = int(max_points)
    except (TypeError, ValueError):
        return queryset
    if max_points <= 0:
        return queryset

    pks = list(queryset.values_list("pk", flat=True))
    if len(pks) <= max_points:
        return queryset

    step = (len(pks) - 1) / (max_points - 1) if max_points > 1 else 0
    return queryset.filter(pk__in=[pks[round(i * step)] for i in range(max_points)])
