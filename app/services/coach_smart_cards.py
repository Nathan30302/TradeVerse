"""
Smart dashboard cards for AI Coach home — only show what's useful now.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.coach_memory import recent_memories


def build_smart_cards(user, *, max_cards: int = 4) -> List[Dict[str, Any]]:
    """
    Relevance-ranked cards for the AI Coach home.
    Each card: id, title, body, tone (neutral|good|warn|danger), action (optional).
    """
    cards: List[Dict[str, Any]] = []
    uid = getattr(user, "id", None)
    if not uid:
        return []

    # Today's focus
    wf = (getattr(user, "weekly_focus_rule", None) or "").strip()
    if wf:
        cards.append(
            {
                "id": "focus",
                "title": "Today’s Focus",
                "body": wf[:220],
                "tone": "neutral",
                "action": None,
            }
        )

    # Focus compliance / discipline
    try:
        from app.services.focus_compliance import measure_focus_compliance

        comp = measure_focus_compliance(user, last_n=10)
        if comp.get("has_focus") and comp.get("sample_size"):
            rate = comp.get("rate")
            tone = "good" if (rate or 0) >= 70 else ("warn" if (rate or 0) >= 40 else "danger")
            cards.append(
                {
                    "id": "discipline",
                    "title": "Discipline Score",
                    "body": f"{comp.get('label')} — {comp.get('detail')}",
                    "tone": tone,
                    "action": None,
                }
            )
    except Exception:
        pass

    # Performance score
    try:
        from app.services.performance_calculator import PerformanceCalculator

        score_obj = PerformanceCalculator(uid).calculate()
        overall = getattr(score_obj, "overall_score", None)
        grade = getattr(score_obj, "grade", None)
        if overall is not None:
            cards.append(
                {
                    "id": "performance",
                    "title": "Performance Score",
                    "body": f"{grade or '—'} · {float(overall):.0f}/100 this week. "
                    f"Driven by discipline, risk, emotion, and consistency.",
                    "tone": "good" if float(overall) >= 70 else ("warn" if float(overall) >= 50 else "danger"),
                    "action": {"label": "Open Performance", "href": "/dashboard/performance"},
                }
            )
    except Exception:
        pass

    # Latest leak from memory or narrative
    mems = recent_memories(uid, limit=6)
    leak_mem = next((m for m in mems if m.get("kind") == "leak"), None)
    if leak_mem:
        cards.append(
            {
                "id": "leak",
                "title": "Latest Leak",
                "body": f"{leak_mem.get('title', '')}. {leak_mem.get('body', '')}"[:240],
                "tone": "warn",
                "action": {"label": "Find My Leaks", "type": "leaks"},
            }
        )
    else:
        try:
            from app.services.ai_coach_context import get_coach_narrative

            cn = get_coach_narrative(user)
            if cn.get("has_data") and cn.get("leak"):
                cards.append(
                    {
                        "id": "leak",
                        "title": "Latest Leak",
                        "body": f"{cn.get('leak')}. {cn.get('summary', '')}"[:240],
                        "tone": "warn",
                        "action": {"label": "Find My Leaks", "type": "leaks"},
                    }
                )
        except Exception:
            pass

    # Recent improvement from memory
    improv = next((m for m in mems if m.get("kind") in ("improvement", "focus")), None)
    if improv and improv.get("kind") == "improvement":
        cards.append(
            {
                "id": "improvement",
                "title": "Recent Improvement",
                "body": f"{improv.get('title')}: {improv.get('body')}"[:240],
                "tone": "good",
                "action": None,
            }
        )

    # Streak (wins/losses)
    try:
        from app.models.trade import Trade

        recent = (
            Trade.query.filter(
                Trade.user_id == uid,
                Trade.status == "CLOSED",
                Trade.profit_loss.isnot(None),
            )
            .order_by(Trade.exit_date.desc().nullslast(), Trade.id.desc())
            .limit(12)
            .all()
        )
        if recent:
            first = float(recent[0].profit_loss or 0)
            streak = 0
            kind = "win" if first > 0 else ("loss" if first < 0 else "flat")
            for t in recent:
                pnl = float(t.profit_loss or 0)
                if kind == "win" and pnl > 0:
                    streak += 1
                elif kind == "loss" and pnl < 0:
                    streak += 1
                else:
                    break
            if streak >= 2 and kind != "flat":
                cards.append(
                    {
                        "id": "streak",
                        "title": "Current Streak",
                        "body": f"{streak} consecutive {kind}{'s' if streak != 1 else ''}.",
                        "tone": "good" if kind == "win" else "danger",
                        "action": None,
                    }
                )
    except Exception:
        pass

    # Suggested action from narrative
    try:
        from app.services.ai_coach_context import get_coach_narrative

        cn = get_coach_narrative(user)
        next_a = (cn.get("next_action") or "").strip()
        if next_a and not any(c.get("id") == "action" for c in cards):
            cards.append(
                {
                    "id": "action",
                    "title": "Suggested Action",
                    "body": next_a[:220],
                    "tone": "neutral",
                    "action": {"label": "Ask the Coach", "type": "ask"},
                }
            )
    except Exception:
        pass

    # Behaviour forecast card
    try:
        from app.services.trade_coach_grades import behaviour_forecast

        forecast = behaviour_forecast(uid)
        if forecast:
            cards.append(
                {
                    "id": "forecast",
                    "title": "Behaviour Forecast",
                    "body": forecast[:260],
                    "tone": "warn",
                    "action": {"label": "Ask the Coach", "type": "ask"},
                }
            )
    except Exception:
        pass

    # De-dupe by id, keep order, cap
    seen = set()
    out: List[Dict[str, Any]] = []
    for c in cards:
        cid = c.get("id")
        if cid in seen:
            continue
        seen.add(cid)
        out.append(c)
        if len(out) >= max_cards:
            break
    return out
