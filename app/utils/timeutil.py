"""
UTC datetime helpers for TradeVerse.

Stored datetimes are naive UTC (SQLite-friendly); we consistently interpret them as UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo


# Common abbreviations used in Settings / Profile (map to IANA for ZoneInfo).
_TZ_ALIASES = {
    "UTC": "UTC",
    "GMT": "UTC",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
}


def resolve_zoneinfo(tz_name: Optional[str]) -> ZoneInfo:
    """Resolve user timezone strings (including EST/CST-style labels) to ZoneInfo."""
    raw = (tz_name or "UTC").strip() or "UTC"
    mapped = _TZ_ALIASES.get(raw.upper(), raw)
    try:
        return ZoneInfo(mapped)
    except Exception:
        return ZoneInfo("UTC")


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
