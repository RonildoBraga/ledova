from datetime import date, datetime, timedelta

from django.utils import timezone


def parse_date_to_timezone_aware(date_value):
    """ "YYYY-MM-DD" string, date or datetime -> aware datetime at the start of that day (None passes through)."""
    if date_value is None:
        return None
    if isinstance(date_value, str):
        date_value = datetime.strptime(date_value, "%Y-%m-%d")
    elif isinstance(date_value, date) and not isinstance(date_value, datetime):
        date_value = datetime.combine(date_value, datetime.min.time())
    if timezone.is_naive(date_value):
        date_value = timezone.make_aware(date_value)
    return date_value


def parse_end_date_inclusive(date_value):
    """Start of the day after `date_value`, so callers can filter with __lt and include the whole end date."""
    if date_value is None:
        return None
    return parse_date_to_timezone_aware(date_value) + timedelta(days=1)
