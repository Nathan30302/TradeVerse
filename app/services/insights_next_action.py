"""
Shared “next action” guidance for Insights pages (Analytics / Patterns / Emotions / Performance).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from flask import url_for
from flask_login import current_user


def build_insights_next_action(
    *,
    page: str = "analytics",
    review_queue: Optional[Dict[str, Any]] = None,
    warning_count: int = 0,
    dangerous_emotion: Optional[str] = None,
) -> Dict[str, str]:
    """
    One clear next step so Insights pages don't compete with each other.
    """
    rq = review_queue or {}
    pending = int(rq.get("total") or 0)
    first_trade = rq.get("first_trade_id")
    focus = ""
    try:
        focus = (getattr(current_user, "weekly_focus_rule", None) or "").strip()
    except Exception:
        focus = ""

    if pending > 0 and first_trade:
        return {
            "eyebrow": "Do this next",
            "title": f"You have {pending} trade{'s' if pending != 1 else ''} waiting for review",
            "body": "Insights are sharper after you write a one-line lesson on closed trades.",
            "cta_label": "Review next trade",
            "cta_url": url_for("trade.view", trade_id=first_trade, review=1),
            "secondary_label": "End of session",
            "secondary_url": url_for("dashboard.eod_ritual"),
        }

    if dangerous_emotion:
        return {
            "eyebrow": "Do this next",
            "title": f"Watch trades tagged “{dangerous_emotion}”",
            "body": "Set a weekly rule that limits size or skips this emotion for 5 sessions.",
            "cta_label": "Set weekly focus",
            "cta_url": url_for("dashboard.weekly_review"),
            "secondary_label": "Open AI Buddy",
            "secondary_url": url_for("dashboard.ai"),
        }

    if warning_count > 0 and page == "patterns":
        return {
            "eyebrow": "Do this next",
            "title": "Turn one weakness into a weekly rule",
            "body": "Pick the loudest pattern warning and make it your only focus for 7 days.",
            "cta_label": "Weekly review",
            "cta_url": url_for("dashboard.weekly_review"),
            "secondary_label": "Add trade with playbook",
            "secondary_url": url_for("trade.add"),
        }

    if not focus:
        return {
            "eyebrow": "Do this next",
            "title": "Set one weekly focus rule",
            "body": "Example: max 2 trades/day, or only trade your A+ playbook setup.",
            "cta_label": "Weekly review",
            "cta_url": url_for("dashboard.weekly_review"),
            "secondary_label": "Open playbook",
            "secondary_url": url_for("playbook.index"),
        }

    return {
        "eyebrow": "Do this next",
        "title": "Stay on your weekly rule",
        "body": focus[:180] + ("…" if len(focus) > 180 else ""),
        "cta_label": "Log a trade",
        "cta_url": url_for("trade.add"),
        "secondary_label": "End of session check",
        "secondary_url": url_for("dashboard.eod_ritual"),
    }
