"""
Shared coaching context for AI Buddy (local + web LLM).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.ai_coaching_note import AICoachingNote
from app.models.trade import Trade


def _safe_getattr(obj, name: str, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def get_active_pinned_note(user_id: int) -> Optional[AICoachingNote]:
    try:
        return (
            AICoachingNote.query.filter(
                AICoachingNote.user_id == user_id,
                AICoachingNote.is_active == True,
            )
            .order_by(
                AICoachingNote.updated_at.desc().nullslast(),
                AICoachingNote.created_at.desc(),
            )
            .first()
        )
    except Exception:
        return None


def get_recent_journal_snippets(user_id: int, limit: int = 5) -> List[Dict[str, str]]:
    """Last closed trades with post-trade notes or lessons (newest first)."""
    snippets: List[Dict[str, str]] = []
    try:
        trades = (
            Trade.query.filter(
                Trade.user_id == user_id,
                Trade.status == "CLOSED",
            )
            .order_by(Trade.exit_date.desc().nullslast(), Trade.id.desc())
            .limit(20)
            .all()
        )
        for t in trades:
            note = (t.post_trade_notes or "").strip()
            lesson = (t.lessons_learned or "").strip()
            combined = note or lesson
            if not combined:
                continue
            if len(combined) > 280:
                combined = combined[:277] + "..."
            snippets.append(
                {
                    "symbol": t.symbol or "?",
                    "pnl": f"{float(t.profit_loss or 0):+.2f}",
                    "emotion": (t.emotion or "").strip(),
                    "text": combined,
                }
            )
            if len(snippets) >= limit:
                break
    except Exception:
        pass
    return snippets


def build_coach_context_dict(user, weekly_stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Structured context for templates and analyzers."""
    wf = (_safe_getattr(user, "weekly_focus_rule", None) or "").strip()
    pinned = get_active_pinned_note(user.id)
    snippets = get_recent_journal_snippets(user.id, limit=5)
    ws = weekly_stats or {}
    return {
        "weekly_focus_rule": wf,
        "pinned_rule": (pinned.pinned_rule if pinned else "") or "",
        "pinned_checklist": pinned.checklist_items() if pinned else [],
        "journal_snippets": snippets,
        "weekly_stats": ws,
    }


def format_coach_context_block(ctx: Dict[str, Any], *, include_stats: bool = True) -> str:
    """Plain-text block injected into local coach and web LLM."""
    lines: List[str] = []
    if include_stats:
        ws = ctx.get("weekly_stats") or {}
        total = int(ws.get("total_trades") or 0)
        if total > 0:
            lines.append(
                "Last 7 days (closed): "
                f"{total} trades, "
                f"{float(ws.get('win_rate') or 0):.1f}% win rate, "
                f"net {float(ws.get('total_pnl') or 0):.2f}, "
                f"avg R:R {float(ws.get('avg_rr') or 0):.2f}."
            )
        else:
            lines.append(
                "Last 7 days: no closed trades logged yet. "
                "Coach the user to log 3+ closed trades with SL, strategy tags, and short notes."
            )
    wf = (ctx.get("weekly_focus_rule") or "").strip()
    if wf:
        lines.append(f"Weekly focus rule (enforce this): {wf}")
    pr = (ctx.get("pinned_rule") or "").strip()
    if pr:
        lines.append(f"Pinned coaching rule: {pr}")
    checklist = ctx.get("pinned_checklist") or []
    if checklist:
        lines.append("Pinned checklist: " + "; ".join(str(x) for x in checklist[:8]))
    snippets = ctx.get("journal_snippets") or []
    if snippets:
        lines.append("Recent journal snippets:")
        for s in snippets:
            if isinstance(s, dict):
                lines.append(
                    f"- {s.get('symbol', '?')} ({s.get('pnl', '')}): {s.get('text', '')}"
                )
    return "\n".join(lines)
