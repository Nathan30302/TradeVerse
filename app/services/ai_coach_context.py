"""
Shared coaching context for AI Buddy (local + web LLM).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.ai_coaching_note import AICoachingNote
from app.models.trade import Trade
from app.services.focus_compliance import measure_focus_compliance


def _safe_getattr(obj, name: str, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        try:
            from app import db

            db.session.rollback()
        except Exception:
            pass
        return default


def get_active_pinned_note(user_id: int) -> Optional[AICoachingNote]:
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            tv = current_app.extensions.get("tradeverse_schema") or {}
            if tv.get("ai_coaching_ready") is False:
                return None
    except Exception:
        pass
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
        try:
            from app import db

            db.session.rollback()
        except Exception:
            pass
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
        try:
            from app import db

            db.session.rollback()
        except Exception:
            pass
    return snippets


def _playbook_adherence(user_id: int, *, last_n: int = 20) -> Dict[str, Any]:
    """How often recent closed trades followed the playbook."""
    out = {
        "setup_count": 0,
        "sample": 0,
        "followed": 0,
        "broken": 0,
        "rate": None,
        "loss_when_broken": 0,
    }
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            tv = current_app.extensions.get("tradeverse_schema") or {}
            if tv.get("playbook_ready") is False:
                return out
        from app.models.playbook_setup import PlaybookSetup

        out["setup_count"] = (
            PlaybookSetup.query.filter_by(user_id=user_id, is_active=True)
            .with_entities(PlaybookSetup.id)
            .count()
        )
    except Exception:
        try:
            from app import db

            db.session.rollback()
        except Exception:
            pass

    try:
        trades = (
            Trade.query.filter(
                Trade.user_id == user_id,
                Trade.status == "CLOSED",
                Trade.profit_loss.isnot(None),
            )
            .order_by(Trade.exit_date.desc().nullslast(), Trade.id.desc())
            .limit(int(last_n))
            .all()
        )
        for t in trades:
            out["sample"] += 1
            if bool(getattr(t, "playbook_followed", False)):
                out["followed"] += 1
            else:
                out["broken"] += 1
                if float(t.profit_loss or 0) < 0:
                    out["loss_when_broken"] += 1
        if out["sample"]:
            out["rate"] = round(out["followed"] / out["sample"] * 100.0, 1)
    except Exception:
        try:
            from app import db

            db.session.rollback()
        except Exception:
            pass
    return out


def _plan_adherence(user_id: int, *, last_n: int = 20) -> Dict[str, Any]:
    """Trade plans linked to recent closed trades — planned vs reviewed."""
    out = {
        "planning": 0,
        "linked_closed": 0,
        "reviewed": 0,
        "avg_grade": None,
    }
    try:
        from app.models.trade_plan import TradePlan

        out["planning"] = (
            TradePlan.query.filter_by(user_id=user_id, status="PLANNING")
            .with_entities(TradePlan.id)
            .count()
        )
        closed_rows = (
            Trade.query.filter(
                Trade.user_id == user_id,
                Trade.status == "CLOSED",
            )
            .order_by(Trade.exit_date.desc().nullslast(), Trade.id.desc())
            .limit(int(last_n))
            .with_entities(Trade.id)
            .all()
        )
        closed_ids = [row[0] for row in closed_rows]
        if not closed_ids:
            return out
        plans = TradePlan.query.filter(
            TradePlan.user_id == user_id,
            (
                TradePlan.executed_trade_id.in_(closed_ids)
                | TradePlan.trade_id.in_(closed_ids)
            ),
        ).all()
        out["linked_closed"] = len(plans)
        grades = []
        for p in plans:
            if (p.status or "").upper() == "REVIEWED":
                out["reviewed"] += 1
            g = (p.trade_grade or "").strip().upper()
            if g in ("A", "B", "C", "D"):
                grades.append({"A": 4, "B": 3, "C": 2, "D": 1}[g])
        if grades:
            out["avg_grade"] = round(sum(grades) / len(grades), 2)
    except Exception:
        try:
            from app import db

            db.session.rollback()
        except Exception:
            pass
    return out


def build_coach_context_dict(user, weekly_stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Structured context for templates and analyzers."""
    wf = (_safe_getattr(user, "weekly_focus_rule", None) or "").strip()
    pinned = get_active_pinned_note(user.id)
    snippets = get_recent_journal_snippets(user.id, limit=5)
    ws = weekly_stats or {}
    compliance = measure_focus_compliance(user, last_n=10)
    playbook = _playbook_adherence(user.id, last_n=20)
    plans = _plan_adherence(user.id, last_n=20)
    return {
        "weekly_focus_rule": wf,
        "pinned_rule": (pinned.pinned_rule if pinned else "") or "",
        "pinned_checklist": pinned.checklist_items() if pinned else [],
        "journal_snippets": snippets,
        "weekly_stats": ws,
        "focus_compliance": compliance,
        "playbook": playbook,
        "plans": plans,
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
    compliance = ctx.get("focus_compliance") or {}
    if compliance.get("has_focus") and compliance.get("sample_size"):
        lines.append(
            "Focus compliance (since rule set / last sample): "
            f"{compliance.get('followed', 0)}/{compliance.get('sample_size', 0)} followed "
            f"({compliance.get('rate')}%). {compliance.get('detail', '')}"
        )
    pr = (ctx.get("pinned_rule") or "").strip()
    if pr:
        lines.append(f"Pinned coaching rule: {pr}")
    checklist = ctx.get("pinned_checklist") or []
    if checklist:
        lines.append("Pinned checklist: " + "; ".join(str(x) for x in checklist[:8]))

    pb = ctx.get("playbook") or {}
    if int(pb.get("setup_count") or 0) > 0 or int(pb.get("sample") or 0) > 0:
        lines.append(
            "Playbook: "
            f"{int(pb.get('setup_count') or 0)} active setups; "
            f"followed on {int(pb.get('followed') or 0)}/{int(pb.get('sample') or 0)} recent closed trades"
            + (f" ({pb.get('rate')}%)" if pb.get("rate") is not None else "")
            + (
                f"; {int(pb.get('loss_when_broken') or 0)} losses when playbook not followed"
                if int(pb.get("loss_when_broken") or 0)
                else ""
            )
            + "."
        )

    plans = ctx.get("plans") or {}
    if int(plans.get("planning") or 0) or int(plans.get("linked_closed") or 0):
        lines.append(
            "Trade plans: "
            f"{int(plans.get('planning') or 0)} still PLANNING; "
            f"{int(plans.get('linked_closed') or 0)} linked to recent closes "
            f"({int(plans.get('reviewed') or 0)} reviewed)"
            + (
                f"; avg grade score {plans.get('avg_grade')} (A=4…D=1)"
                if plans.get("avg_grade") is not None
                else ""
            )
            + "."
        )

    snippets = ctx.get("journal_snippets") or []
    if snippets:
        lines.append("Recent journal snippets:")
        for s in snippets:
            if isinstance(s, dict):
                lines.append(
                    f"- {s.get('symbol', '?')} ({s.get('pnl', '')}): {s.get('text', '')}"
                )
    return "\n".join(lines)
