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
            "eyebrow": "Worth doing now",
            "title": f"{pending} closed trade{'s' if pending != 1 else ''} still need a note",
            "body": "One line on what you learned makes the rest of this page useful.",
            "cta_label": "Review next trade",
            "cta_url": url_for("trade.view", trade_id=first_trade, review=1),
            "secondary_label": "End of session",
            "secondary_url": url_for("dashboard.eod_ritual"),
        }

    if dangerous_emotion:
        return {
            "eyebrow": "Worth doing now",
            "title": f"Trades tagged “{dangerous_emotion}” are costing you",
            "body": "Give yourself one rule for the week: smaller size, or skip this feeling entirely.",
            "cta_label": "Set weekly focus",
            "cta_url": url_for("dashboard.weekly_review"),
            "secondary_label": "Open AI Coach",
            "secondary_url": url_for("dashboard.ai"),
        }

    if warning_count > 0 and page == "patterns":
        return {
            "eyebrow": "Worth doing now",
            "title": "Pick one weak spot and make it this week’s rule",
            "body": "One warning. Seven days. Leave the rest alone until that one’s quieter.",
            "cta_label": "Weekly review",
            "cta_url": url_for("dashboard.weekly_review"),
            "secondary_label": "Add trade with playbook",
            "secondary_url": url_for("trade.add"),
        }

    if not focus:
        return {
            "eyebrow": "Worth doing now",
            "title": "Name one rule for this week",
            "body": "Two trades a day, or only the setup you already trust. One sentence is enough.",
            "cta_label": "Weekly review",
            "cta_url": url_for("dashboard.weekly_review"),
            "secondary_label": "Open playbook",
            "secondary_url": url_for("playbook.index"),
        }

    return {
        "eyebrow": "This week",
        "title": "Stay with the rule you already set",
        "body": focus[:180] + ("…" if len(focus) > 180 else ""),
        "cta_label": "Log a trade",
        "cta_url": url_for("trade.add"),
        "secondary_label": "End of session check",
        "secondary_url": url_for("dashboard.eod_ritual"),
    }
