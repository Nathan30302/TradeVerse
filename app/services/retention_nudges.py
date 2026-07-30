"""
In-app retention nudges — soft welcome-back / session / focus / coach prompts.

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
    Pick one soft nudge (priority: idle → EOD → coach check-in → focus).
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
            "secondary_label": "Talk to Coach",
            "secondary_url": url_for("dashboard.ai"),
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

    # Coach check-in: no closed trade / journal activity recently
    coach_nudge = _coach_proactive_nudge(user, now)
    if coach_nudge:
        return coach_nudge

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
                "One rule for the week beats ten vague goals — AI Coach will hold you to it."
                if not wf
                else "Your focus is over a week old. Renew it from this week’s lessons."
            ),
            "primary_label": "Weekly review",
            "primary_url": url_for("dashboard.weekly_review"),
            "secondary_label": "AI Coach",
            "secondary_url": url_for("dashboard.ai"),
            "dismiss_key": "tv_nudge_focus_" + ("empty" if not wf else "stale"),
        }

    return None


def _coach_proactive_nudge(user, now: datetime) -> Optional[Dict[str, Any]]:
    """Proactive coach check-ins from journal silence / losing streak / NY session shift."""
    uid = _safe_getattr(user, "id", None)
    if not uid:
        return None
    try:
        from app.models.trade import Trade

        last = (
            Trade.query.filter(
                Trade.user_id == uid,
                Trade.status == "CLOSED",
                Trade.profit_loss.isnot(None),
            )
            .order_by(Trade.exit_date.desc().nullslast(), Trade.id.desc())
            .first()
        )
    except Exception:
        last = None

    if last is None:
        created = _as_utc(_safe_getattr(user, "created_at", None))
        if created and (now - created) >= timedelta(days=2):
            return {
                "kind": "coach_journal",
                "title": "Your coach is ready when you are",
                "body": "Close one trade with SL, strategy tag, and a one-line note — then ask for your first leak.",
                "primary_label": "Talk to Coach",
                "primary_url": url_for("dashboard.ai"),
                "secondary_label": "Log a trade",
                "secondary_url": url_for("trade.add"),
                "dismiss_key": "tv_nudge_coach_empty",
            }
        return None

    exit_at = _as_utc(getattr(last, "exit_date", None) or getattr(last, "entry_date", None))
    if exit_at and (now - exit_at) >= timedelta(days=4):
        days = max(1, int((now - exit_at).total_seconds() // 86400))
        return {
            "kind": "coach_journal",
            "title": f"You haven’t journaled in {days} days",
            "body": "Is everything okay? A short note or a voice check-in with AI Coach keeps the edge sharp.",
            "primary_label": "Talk to Coach",
            "primary_url": url_for("dashboard.ai"),
            "secondary_label": "Log a trade",
            "secondary_url": url_for("trade.add"),
            "dismiss_key": f"tv_nudge_coach_quiet_{days}",
        }

    # Losing streak check-in
    try:
        from app.models.trade import Trade

        recent = (
            Trade.query.filter(
                Trade.user_id == uid,
                Trade.status == "CLOSED",
                Trade.profit_loss.isnot(None),
            )
            .order_by(Trade.exit_date.desc().nullslast(), Trade.id.desc())
            .limit(5)
            .all()
        )
        loss_streak = 0
        for t in recent:
            if float(t.profit_loss or 0) < 0:
                loss_streak += 1
            else:
                break
        if loss_streak >= 3:
            return {
                "kind": "coach_streak",
                "title": f"{loss_streak} losses in a row",
                "body": "Worth a pause. Review a past winner or run Find My Leaks before the next entry.",
                "primary_label": "Find My Leaks",
                "primary_url": url_for("dashboard.ai"),
                "secondary_label": "End of session",
                "secondary_url": url_for("dashboard.eod_ritual"),
                "dismiss_key": f"tv_nudge_coach_loss_{loss_streak}",
            }
    except Exception:
        pass

    # Session shift: majority of last 10 in New York
    try:
        from app.models.trade import Trade

        sample = (
            Trade.query.filter(
                Trade.user_id == uid,
                Trade.status == "CLOSED",
            )
            .order_by(Trade.exit_date.desc().nullslast(), Trade.id.desc())
            .limit(10)
            .all()
        )
        if len(sample) >= 6:
            ny = sum(1 for t in sample if (t.session_type or "").lower() in ("new york", "ny", "newyork"))
            if ny >= 5:
                return {
                    "kind": "coach_session",
                    "title": "More New York session trades lately",
                    "body": "How has that been going? Ask the coach to compare NY vs your other sessions.",
                    "primary_label": "Ask the Coach",
                    "primary_url": url_for("dashboard.ai"),
                    "secondary_label": "Analytics",
                    "secondary_url": url_for("dashboard.analytics"),
                    "dismiss_key": "tv_nudge_coach_ny",
                }
    except Exception:
        pass

    return None
