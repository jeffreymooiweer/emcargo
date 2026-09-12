"""Database times must retain their UTC meaning when sent to the browser."""
from datetime import datetime, timedelta, timezone

from app.core.dates import utc_timestamp


def test_naive_database_time_is_labelled_utc():
    assert utc_timestamp(datetime(2026, 9, 12, 8, 20)).isoformat() == "2026-09-12T08:20:00+00:00"


def test_explicit_offset_keeps_the_same_instant():
    local = datetime(2026, 9, 12, 10, 20, tzinfo=timezone(timedelta(hours=2)))
    assert utc_timestamp(local).isoformat() == "2026-09-12T08:20:00+00:00"
