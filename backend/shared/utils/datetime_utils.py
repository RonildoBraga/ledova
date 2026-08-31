"""
Datetime utility functions for handling timezone-aware datetime conversions.
"""

from datetime import datetime, timedelta

from django.utils import timezone


def parse_date_to_timezone_aware(date_value):
    """
    Convert a date string or naive datetime to a timezone-aware datetime.

    Args:
        date_value: Can be:
            - str: Date string in YYYY-MM-DD format
            - datetime: Naive or aware datetime object
            - None: Returns None

    Returns:
        datetime: Timezone-aware datetime at start of day, or None if input is None

    Examples:
        >>> parse_date_to_timezone_aware("2025-09-30")
        datetime.datetime(2025, 9, 30, 0, 0, tzinfo=<UTC>)

        >>> parse_date_to_timezone_aware(datetime(2025, 9, 30))
        datetime.datetime(2025, 9, 30, 0, 0, tzinfo=<UTC>)
    """
    if date_value is None:
        return None

    # Convert string to datetime
    if isinstance(date_value, str):
        date_value = datetime.strptime(date_value, "%Y-%m-%d")

    # Make timezone-aware if naive
    if timezone.is_naive(date_value):
        date_value = timezone.make_aware(date_value)

    return date_value


def parse_end_date_inclusive(date_value):
    """
    Convert a date to a timezone-aware datetime representing the end of that day.

    This is useful for range queries where you want to include the entire end date.
    Returns the start of the next day, so you can use __lt instead of __lte.

    Args:
        date_value: Can be:
            - str: Date string in YYYY-MM-DD format
            - datetime: Naive or aware datetime object
            - None: Returns None

    Returns:
        datetime: Timezone-aware datetime at start of next day, or None if input is None

    Examples:
        >>> parse_end_date_inclusive("2025-09-30")
        datetime.datetime(2025, 10, 1, 0, 0, tzinfo=<UTC>)

        # Usage in query:
        # queryset.filter(date__lt=parse_end_date_inclusive("2025-09-30"))
        # This includes all records from 2025-09-30 23:59:59.999999
    """
    if date_value is None:
        return None

    # Parse to timezone-aware datetime
    aware_datetime = parse_date_to_timezone_aware(date_value)

    # Add one day to make it inclusive when using __lt
    return aware_datetime + timedelta(days=1)
