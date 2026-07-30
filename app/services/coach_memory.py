"""
Coach memory — long-term observations the AI Coach builds over time.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app import db
from app.models.coach_memory import CoachMemory


def remember(
    user_id: int,
    *,
    kind: str,
    title: str,
    body: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Optional[CoachMemory]:
    """Persist a short coaching memory entry."""
    title = (title or "").strip()[:200]
    body = (body or "").strip()[:2000]
    kind = (kind or "note").strip()[:40] or "note"
    if not title and not body:
        return None
    try:
        import json

        row = CoachMemory(
            user_id=int(user_id),
            kind=kind,
            title=title or kind.replace("_", " ").title(),
            body=body,
            meta_json=json.dumps(meta or {})[:4000],
        )
        db.session.add(row)
        db.session.commit()
        return row
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


def recent_memories(user_id: int, *, limit: int = 8) -> List[Dict[str, Any]]:
    """Latest coaching memories for context injection / UI."""
    try:
        rows = (
            CoachMemory.query.filter_by(user_id=int(user_id))
            .order_by(CoachMemory.created_at.desc())
            .limit(int(limit))
            .all()
        )
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "kind": r.kind,
                "title": r.title,
                "body": r.body,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return out


def format_memory_block(user_id: int, *, limit: int = 6) -> str:
    """Plain-text block for LLM / local coach context."""
    mems = recent_memories(user_id, limit=limit)
    if not mems:
        return ""
    lines = ["Coaching memory (recent):"]
    for m in mems:
        lines.append(f"- [{m.get('kind')}] {m.get('title')}: {m.get('body')}")
    return "\n".join(lines)


def remember_trade_doctor(user_id: int, result: Dict[str, Any]) -> None:
    """Store a leak diagnosis as memory."""
    leak = (result.get("leak") or "").strip()
    if not leak or leak in ("No recent closed trades", "Need more signal"):
        return
    evidence = result.get("evidence") or []
    ev = evidence[0] if evidence else ""
    remember(
        user_id,
        kind="leak",
        title=f"Leak: {leak[:120]}",
        body=(ev or result.get("suggested_focus") or leak)[:800],
        meta={"sample_size": result.get("sample_size")},
    )


def remember_focus(user_id: int, rule: str) -> None:
    rule = (rule or "").strip()
    if not rule:
        return
    remember(
        user_id,
        kind="focus",
        title="Weekly focus set",
        body=rule[:800],
    )


def record_improvement_snapshot(user_id: int) -> Optional[str]:
    """
    Compare this month vs last month trade count / overtrading proxy.
    Stores an improvement memory when meaningful.
    """
    from datetime import timedelta

    from app.models.trade import Trade
    from app.utils.timeutil import utc_now

    now = utc_now()
    this_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if this_start.month == 1:
        prev_start = this_start.replace(year=this_start.year - 1, month=12)
    else:
        prev_start = this_start.replace(month=this_start.month - 1)
    prev_end = this_start

    def _count_and_avg_day(start, end):
        rows = (
            Trade.query.filter(
                Trade.user_id == int(user_id),
                Trade.status == "CLOSED",
                Trade.profit_loss.isnot(None),
                Trade.exit_date >= start,
                Trade.exit_date < end,
            ).all()
        )
        if not rows:
            return 0, 0.0
        by_day = {}
        for t in rows:
            d = (t.exit_date or t.entry_date)
            if not d:
                continue
            key = d.date().isoformat()
            by_day[key] = by_day.get(key, 0) + 1
        avg = sum(by_day.values()) / max(1, len(by_day))
        return len(rows), avg

    try:
        this_n, this_avg = _count_and_avg_day(this_start, now + timedelta(days=1))
        prev_n, prev_avg = _count_and_avg_day(prev_start, prev_end)
    except Exception:
        return None

    if prev_n < 5 or this_n < 3:
        return None

    # Overtrading proxy: avg trades/day
    if prev_avg > 0 and this_avg < prev_avg:
        drop = (prev_avg - this_avg) / prev_avg * 100
        if drop >= 15:
            msg = (
                f"Last month you averaged {prev_avg:.1f} trades/day; "
                f"this month you’re at {this_avg:.1f} (−{drop:.0f}%). Solid reduction in overtrading pace."
            )
            remember(user_id, kind="improvement", title="Overtrading down", body=msg)
            return msg

    # Win rate improvement if we can compute quickly
    def _wr(start, end):
        rows = Trade.query.filter(
            Trade.user_id == int(user_id),
            Trade.status == "CLOSED",
            Trade.profit_loss.isnot(None),
            Trade.exit_date >= start,
            Trade.exit_date < end,
        ).all()
        if len(rows) < 5:
            return None
        wins = sum(1 for t in rows if float(t.profit_loss or 0) > 0)
        return wins / len(rows) * 100

    try:
        wr_now = _wr(this_start, now + timedelta(days=1))
        wr_prev = _wr(prev_start, prev_end)
        if wr_now is not None and wr_prev is not None and wr_now >= wr_prev + 5:
            msg = (
                f"Win rate improved from {wr_prev:.0f}% last month to {wr_now:.0f}% this month. "
                "Keep the same process that earned it."
            )
            remember(user_id, kind="improvement", title="Win rate up", body=msg)
            return msg
    except Exception:
        pass
    return None
