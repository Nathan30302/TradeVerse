"""
UTC datetime helpers for TradeVerse.

Stored datetimes are naive UTC (SQLite-friendly); we consistently interpret them as UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """
    Current instant in UTC as naive datetime.

    Replaces deprecated datetime.utcnow() without changing comparison semantics
    with existing ORM rows.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_datetime_optional(value: Optional[str]) -> Optional[datetime]:
    """
    Parse ISO datetime strings from forms (datetime-local, JS ISO with Z).

    Returns naive UTC for consistent ORM storage. Returns None if missing/blank.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
