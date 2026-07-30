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
