"""Normalize date filters before database drivers bind their values."""
from datetime import datetime, timezone


def utc_filter_bound(value: datetime) -> datetime:
    """Preserve legacy UTC-naive filters and normalize explicit offsets.

    SQLite drops a bound datetime's timezone instead of converting it. An
    explicit local offset must therefore be converted before it reaches the
    driver, or a calendar-day filter excludes early records and adds late ones.
    """
    return value.astimezone(timezone.utc) if value.tzinfo is not None else value
