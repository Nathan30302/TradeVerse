"""
Short TTL caches for expensive AI dashboard helpers.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Tuple

from app.services.ai_insights import AIAnalyzer

_weekly: Dict[int, Tuple[float, dict]] = {}
_last_insight: Dict[int, Tuple[float, str]] = {}
_TTL_WEEKLY = 600  # 10 minutes
_TTL_INSIGHT = 300  # 5 minutes
_TTL_BRIEFING = 300  # 5 minutes
_TTL_IMPROVEMENT = 86400  # once per day

_briefing: Dict[int, Tuple[float, dict]] = {}
_improvement_at: Dict[int, float] = {}


def get_cached_weekly_review(user_id: int) -> dict:
    now = time.time()
    hit = _weekly.get(user_id)
    if hit and hit[0] > now:
        return dict(hit[1])
    data = AIAnalyzer(user_id).get_weekly_review() or {}
    _weekly[user_id] = (now + _TTL_WEEKLY, data)
    return dict(data)


def get_cached_last_trade_insight(user_id: int) -> str:
    now = time.time()
    hit = _last_insight.get(user_id)
    if hit and hit[0] > now:
        return hit[1]
    text = AIAnalyzer(user_id).get_last_trade_insight() or ""
    _last_insight[user_id] = (now + _TTL_INSIGHT, text)
    return text


def get_cached_morning_briefing(user_id: int, user_name: str = "") -> dict:
    now = time.time()
    hit = _briefing.get(user_id)
    if hit and hit[0] > now:
        return dict(hit[1])
    data = AIAnalyzer(user_id).get_morning_briefing(user_name=user_name) or {}
    _briefing[user_id] = (now + _TTL_BRIEFING, data)
    return dict(data)


def maybe_record_improvement_snapshot(user_id: int) -> None:
    """At most once per day — avoid write-on-read month scans every AI page load."""
    now = time.time()
    due = _improvement_at.get(int(user_id), 0.0)
    if due > now:
        return
    _improvement_at[int(user_id)] = now + _TTL_IMPROVEMENT
    try:
        from app.services.coach_memory import record_improvement_snapshot

        record_improvement_snapshot(int(user_id))
    except Exception:
        pass
