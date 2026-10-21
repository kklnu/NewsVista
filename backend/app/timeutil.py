"""All timestamps are timezone-aware UTC."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def window_start(now: datetime, retention_hours: int) -> datetime:
    """Oldest publication time still inside the rolling news window."""
    return now - timedelta(hours=retention_hours)


def iso(value: datetime | None) -> str | None:
    value = as_utc(value)
    return value.isoformat().replace("+00:00", "Z") if value else None
