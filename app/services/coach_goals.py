"""
Goals and challenges progress — evidence from the journal.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app import db
from app.models.coach_goal import CHALLENGE_CATALOG, CoachChallenge, CoachGoal
from app.models.trade import Trade
from app.utils.timeutil import utc_now


def _closed_since(user_id: int, since: datetime) -> List[Trade]:
    try:
        return (
            Trade.query.filter(
                Trade.user_id == int(user_id),
                Trade.status == "CLOSED",
                Trade.profit_loss.isnot(None),
                Trade.exit_date >= since,
            )
            .order_by(Trade.exit_date.asc())
            .all()
        )
    except Exception:
        return []


def refresh_goal_progress(goal: CoachGoal) -> CoachGoal:
    """Update progress_pct / detail from journal."""
    since = goal.starts_at or utc_now() - timedelta(days=30)
    trades = _closed_since(goal.user_id, since)
    metric = (goal.metric or "custom").strip()
    target = float(goal.target_value or 0) or None
    detail = ""
    pct = 0.0

    if metric == "max_trades_day":
        by_day: Dict[str, int] = defaultdict(int)
        for t in trades:
            d = (t.exit_date or t.entry_date)
            if d:
                by_day[d.date().isoformat()] += 1
        limit = int(target or 2)
        ok_days = sum(1 for c in by_day.values() if c <= limit)
        total_days = max(1, len(by_day))
        pct = ok_days / total_days * 100 if by_day else 0.0
        detail = f"{ok_days}/{len(by_day) or 0} trading days stayed ≤{limit} trades."
    elif metric == "risk_pct":
        want = float(target or 1.0)
        tagged = [t for t in trades if t.risk_percentage is not None]
        ok = sum(1 for t in tagged if abs(float(t.risk_percentage) - want) <= 0.25)
        pct = (ok / len(tagged) * 100) if tagged else 0.0
        detail = f"{ok}/{len(tagged)} trades near {want}% risk."
    elif metric == "no_revenge":
        bad = {
            "revenge",
            "revenge trading",
            "fomo",
            "tilt",
            "angry",
            "greedy",
        }
        days_needed = int(target or 30)
        clean_days = set()
        dirty_days = set()
        for t in trades:
            d = (t.exit_date or t.entry_date)
            if not d:
                continue
            key = d.date().isoformat()
            emo = (t.emotion or "").strip().lower()
            if emo in bad or any(x in emo for x in ("revenge", "fomo", "tilt")):
                dirty_days.add(key)
            else:
                clean_days.add(key)
        clean_only = clean_days - dirty_days
        pct = min(100.0, len(clean_only) / max(1, days_needed) * 100)
        detail = f"{len(clean_only)} clean days toward {days_needed} (no revenge/FOMO tags)."
    elif metric == "rule_adherence":
        want = float(target or 90)
        try:
            from app.models.user import User
            from app.services.focus_compliance import measure_focus_compliance

            user = User.query.get(goal.user_id)
            comp = measure_focus_compliance(user, last_n=20) if user else {}
            rate = float(comp.get("rate") or 0)
            pct = min(100.0, rate / want * 100) if want else rate
            detail = f"Focus adherence {rate:.0f}% (goal {want:.0f}%)."
        except Exception:
            detail = "Set a weekly focus to track rule adherence."
            pct = 0.0
    elif metric == "journal_days":
        days_needed = int(target or 7)
        days = set()
        for t in trades:
            d = (t.exit_date or t.entry_date)
            note = (t.post_trade_notes or t.lessons_learned or "").strip()
            if d and note:
                days.add(d.date().isoformat())
        pct = min(100.0, len(days) / max(1, days_needed) * 100)
        detail = f"{len(days)}/{days_needed} days with post-trade notes."
    else:
        detail = goal.target_text or "Custom goal — ask the coach to review."
        pct = float(goal.progress_pct or 0)

    goal.progress_pct = round(pct, 1)
    goal.progress_detail = detail[:400]
    if pct >= 100 and goal.status == "active":
        goal.status = "completed"
        goal.completed_at = utc_now()
    goal.updated_at = utc_now()
    return goal


def list_goals(user_id: int) -> List[Dict[str, Any]]:
    rows = (
        CoachGoal.query.filter_by(user_id=int(user_id))
        .order_by(CoachGoal.created_at.desc())
        .limit(20)
        .all()
    )
    out = []
    for g in rows:
        if g.status == "active":
            refresh_goal_progress(g)
        out.append(_goal_dict(g))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return out


def _goal_dict(g: CoachGoal) -> Dict[str, Any]:
    return {
        "id": g.id,
        "title": g.title,
        "metric": g.metric,
        "target_value": g.target_value,
        "target_text": g.target_text,
        "status": g.status,
        "progress_pct": g.progress_pct,
        "progress_detail": g.progress_detail,
        "starts_at": g.starts_at.isoformat() if g.starts_at else None,
        "ends_at": g.ends_at.isoformat() if g.ends_at else None,
    }


def create_goal(
    user_id: int,
    *,
    title: str,
    metric: str = "custom",
    target_value: Optional[float] = None,
    target_text: str = "",
    days: Optional[int] = None,
) -> CoachGoal:
    ends = utc_now() + timedelta(days=int(days)) if days else None
    g = CoachGoal(
        user_id=int(user_id),
        title=(title or "").strip()[:200] or "Coaching goal",
        metric=(metric or "custom").strip()[:40],
        target_value=target_value,
        target_text=(target_text or "").strip()[:400],
        ends_at=ends,
    )
    refresh_goal_progress(g)
    db.session.add(g)
    db.session.commit()
    try:
        from app.services.coach_memory import remember

        remember(user_id, kind="goal", title=f"Goal: {g.title}", body=g.progress_detail or g.target_text)
    except Exception:
        pass
    return g


def refresh_challenge_progress(ch: CoachChallenge) -> CoachChallenge:
    since = ch.starts_at or utc_now() - timedelta(days=30)
    trades = _closed_since(ch.user_id, since)
    code = (ch.code or "").strip()
    count = 0
    detail = ""

    if code == "no_sl_move":
        # Proxy: trades with SL logged + no "moved stop" in notes
        for t in trades:
            has_sl = t.stop_loss is not None
            notes = ((t.post_trade_notes or "") + " " + (t.lessons_learned or "")).lower()
            moved = "moved stop" in notes or "moved sl" in notes or "widened stop" in notes
            if has_sl and not moved:
                count += 1
            elif moved:
                break  # streak broken — still count completed clean ones before break? count all clean
        count = sum(
            1
            for t in trades
            if t.stop_loss is not None
            and "moved stop" not in ((t.post_trade_notes or "") + " " + (t.lessons_learned or "")).lower()
            and "moved sl" not in ((t.post_trade_notes or "") + " " + (t.lessons_learned or "")).lower()
        )
        detail = f"{count} closed trades with SL and no ‘moved stop’ note."
    elif code == "journal_7":
        days = set()
        for t in trades:
            d = t.exit_date or t.entry_date
            note = (t.post_trade_notes or t.lessons_learned or "").strip()
            if d and note:
                days.add(d.date().isoformat())
        count = len(days)
        detail = f"{count} distinct days with notes."
    elif code == "risk_1pct":
        count = sum(
            1
            for t in trades
            if t.risk_percentage is not None and 0.75 <= float(t.risk_percentage) <= 1.25
        )
        detail = f"{count} trades near 1% risk."
    elif code == "no_revenge":
        bad = ("revenge", "fomo", "tilt", "angry", "greedy")
        days_ok = set()
        days_bad = set()
        for t in trades:
            d = t.exit_date or t.entry_date
            if not d:
                continue
            key = d.date().isoformat()
            emo = (t.emotion or "").lower()
            if any(b in emo for b in bad):
                days_bad.add(key)
            else:
                days_ok.add(key)
        count = len(days_ok - days_bad)
        detail = f"{count} clean emotional days."
    elif code == "max_two":
        by_day: Dict[str, int] = defaultdict(int)
        for t in trades:
            d = t.exit_date or t.entry_date
            if d:
                by_day[d.date().isoformat()] += 1
        count = sum(1 for c in by_day.values() if c <= 2)
        detail = f"{count} days with ≤2 trades."
    else:
        detail = "Unknown challenge type."

    ch.progress_count = int(count)
    ch.progress_detail = detail[:400]
    target = int(ch.target_count or 1)
    if count >= target and ch.status == "active":
        ch.status = "completed"
        ch.completed_at = utc_now()
        ch.review_text = (
            f"Challenge complete: {ch.title}. {detail} "
            f"Next: lock this as a weekly focus so it sticks."
        )
        try:
            from app.services.coach_memory import remember

            remember(
                ch.user_id,
                kind="challenge",
                title=f"Completed: {ch.title}",
                body=ch.review_text,
            )
        except Exception:
            pass
    if ch.ends_at and utc_now() > ch.ends_at and ch.status == "active" and count < target:
        ch.status = "failed"
        ch.review_text = f"Time ran out on “{ch.title}”. Progress: {detail}. Restart when ready."
    ch.updated_at = utc_now()
    return ch


def list_challenges(user_id: int) -> List[Dict[str, Any]]:
    rows = (
        CoachChallenge.query.filter_by(user_id=int(user_id))
        .order_by(CoachChallenge.created_at.desc())
        .limit(20)
        .all()
    )
    out = []
    for ch in rows:
        if ch.status == "active":
            refresh_challenge_progress(ch)
        out.append(_challenge_dict(ch))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return out


def _challenge_dict(ch: CoachChallenge) -> Dict[str, Any]:
    return {
        "id": ch.id,
        "code": ch.code,
        "title": ch.title,
        "description": ch.description,
        "status": ch.status,
        "target_count": ch.target_count,
        "progress_count": ch.progress_count,
        "progress_detail": ch.progress_detail,
        "review_text": ch.review_text,
        "starts_at": ch.starts_at.isoformat() if ch.starts_at else None,
        "ends_at": ch.ends_at.isoformat() if ch.ends_at else None,
    }


def start_challenge(user_id: int, code: str) -> Optional[CoachChallenge]:
    catalog = next((c for c in CHALLENGE_CATALOG if c["code"] == code), None)
    if not catalog:
        return None
    # Only one active of same code
    existing = CoachChallenge.query.filter_by(
        user_id=int(user_id), code=code, status="active"
    ).first()
    if existing:
        refresh_challenge_progress(existing)
        db.session.commit()
        return existing
    days = int(catalog.get("days") or 14)
    ch = CoachChallenge(
        user_id=int(user_id),
        code=catalog["code"],
        title=catalog["title"],
        description=catalog["description"],
        target_count=int(catalog["target_count"]),
        ends_at=utc_now() + timedelta(days=days),
    )
    refresh_challenge_progress(ch)
    db.session.add(ch)
    db.session.commit()
    try:
        from app.services.coach_memory import remember

        remember(user_id, kind="challenge", title=f"Started: {ch.title}", body=ch.description[:400])
    except Exception:
        pass
    return ch


def catalog() -> List[Dict[str, Any]]:
    return list(CHALLENGE_CATALOG)
