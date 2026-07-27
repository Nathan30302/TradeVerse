"""
In-app retention nudges — soft welcome-back / session / focus prompts.

Separate from email CLI (``flask send-nudges``). These are dismissible UI cues.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from flask import url_for


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_getattr(obj, name: str, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def build_retention_nudge(
    user,
    *,
    review_queue: Optional[Dict[str, Any]] = None,
    idle_days: int = 3,
) -> Optional[Dict[str, Any]]:
    """
    Pick one soft nudge for the dashboard (priority: idle → EOD review → focus).

    Returns None when nothing useful to show.
    """
    if not user:
        return None

    now = datetime.now(timezone.utc)
    rq = review_queue or {}
    last_login = _as_utc(_safe_getattr(user, "last_login", None))
    created = _as_utc(_safe_getattr(user, "created_at", None))
    anchor = last_login or created
    if anchor and (now - anchor) >= timedelta(days=max(1, int(idle_days))):
        days = max(1, int((now - anchor).total_seconds() // 86400))
        return {
            "kind": "idle",
            "title": f"Welcome back — {days} day{'s' if days != 1 else ''} away",
            "body": "One honest log or a quick end-of-session review restarts the streak.",
            "primary_label": "Log a trade",
            "primary_url": url_for("trade.add"),
            "secondary_label": "End of session",
            "secondary_url": url_for("dashboard.eod_ritual"),
            "dismiss_key": f"tv_nudge_idle_{days}",
        }

    review_total = int(rq.get("total") or 0)
    first_id = rq.get("first_trade_id")
    if review_total > 0 and first_id:
        return {
            "kind": "eod",
            "title": f"{review_total} trade{'s' if review_total != 1 else ''} waiting for review",
            "body": "Close the loop before the next session — notes beat memory.",
            "primary_label": "Review next",
            "primary_url": url_for("trade.view", trade_id=first_id, review=1),
            "secondary_label": "End of session",
            "secondary_url": url_for("dashboard.eod_ritual"),
            "dismiss_key": f"tv_nudge_eod_{first_id}",
        }

    wf = (_safe_getattr(user, "weekly_focus_rule", None) or "").strip()
    set_at = _as_utc(_safe_getattr(user, "weekly_focus_set_at", None))
    focus_stale = False
    if not wf:
        focus_stale = True
    elif set_at and (now - set_at) >= timedelta(days=7):
        focus_stale = True

    if focus_stale:
        return {
            "kind": "focus",
            "title": "Set one weekly focus rule" if not wf else "Refresh your weekly focus",
            "body": (
                "One rule for the week beats ten vague goals — AI Buddy and the journal will hold you to it."
                if not wf
                else "Your focus is over a week old. Renew it from this week’s lessons."
            ),
            "primary_label": "Weekly review",
            "primary_url": url_for("dashboard.weekly_review"),
            "secondary_label": "AI Buddy",
            "secondary_url": url_for("dashboard.ai"),
            "dismiss_key": "tv_nudge_focus_" + ("empty" if not wf else "stale"),
        }

    return None
