"""
Retention helpers — daily loop, review queue, journaling streak, lifecycle context.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import load_only

from app import db
from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from app.models.performance_score import PerformanceScore
from app.services.ai_insights import AIAnalyzer
from app.services.performance_calculator import calculate_weekly_score
from app.utils.timeutil import utc_now


def _rollback_quietly() -> None:
    """Clear an aborted Postgres transaction so later queries can proceed."""
    try:
        db.session.rollback()
    except Exception:
        pass


def trade_needs_review(trade: Trade) -> bool:
    """True when a closed trade has no post-trade reflection."""
    if trade.status != 'CLOSED':
        return False
    notes = (trade.post_trade_notes or '').strip()
    lessons = (trade.lessons_learned or '').strip()
    return not notes and not lessons


def count_pending_trade_reviews(user_id: int) -> int:
    """Count closed trades missing post-trade reflection (SQL-only, for global UI)."""
    try:
        return int(
            db.session.query(func.count(Trade.id))
            .filter(
                Trade.user_id == user_id,
                Trade.status == 'CLOSED',
                or_(Trade.post_trade_notes.is_(None), Trade.post_trade_notes == ''),
                or_(Trade.lessons_learned.is_(None), Trade.lessons_learned == ''),
            )
            .scalar()
            or 0
        )
    except Exception:
        _rollback_quietly()
        return 0


def get_today_strip_context(user) -> Dict[str, Any]:
    """Lightweight counts for the mobile today strip (no heavy trade scans)."""
    uid = user.id
    trades_pending = count_pending_trade_reviews(uid)
    plans_count = 0
    try:
        plans_count = int(
            db.session.query(func.count(TradePlan.id))
            .filter(
                TradePlan.user_id == uid,
                TradePlan.status == 'EXECUTED',
            )
            .scalar()
            or 0
        )
    except Exception:
        _rollback_quietly()
        plans_count = 0
    tz = getattr(user, 'timezone', None) or 'UTC'
    return {
        'reviews': trades_pending + int(plans_count or 0),
        'streak': get_journaling_streak(uid, tz),
    }


def get_review_queue(user_id: int) -> Dict[str, Any]:
    """Closed trades and executed plans waiting for review."""
    pending_trades: List[Trade] = []
    try:
        rows = (
            Trade.query.options(
                load_only(
                    Trade.id,
                    Trade.status,
                    Trade.post_trade_notes,
                    Trade.lessons_learned,
                    Trade.exit_date,
                )
            )
            .filter(
                Trade.user_id == user_id,
                Trade.status == 'CLOSED',
            )
            .order_by(Trade.exit_date.desc().nullslast(), Trade.id.desc())
            .limit(80)
            .all()
        )
        pending_trades = [t for t in rows if trade_needs_review(t)]
    except Exception:
        _rollback_quietly()
        pending_trades = []

    plans_count = 0
    try:
        plans_count = int(
            db.session.query(func.count(TradePlan.id))
            .filter(
                TradePlan.user_id == user_id,
                TradePlan.status == 'EXECUTED',
            )
            .scalar()
            or 0
        )
    except Exception:
        _rollback_quietly()
        plans_count = 0

    first_id = pending_trades[0].id if pending_trades else None
    return {
        'trades_count': len(pending_trades),
        'plans_count': int(plans_count or 0),
        'total': len(pending_trades) + int(plans_count or 0),
        'first_trade_id': first_id,
    }


def _activity_dates_for_user(user_id: int, tz_name: str = 'UTC') -> set[date]:
    """Calendar dates with journal activity (log, plan, or review)."""
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo((tz_name or 'UTC').strip() or 'UTC')
    except Exception:
        tz = timezone.utc

    def _to_local_day(dt: Optional[datetime]) -> Optional[date]:
        if not dt:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz).date()

    days: set[date] = set()
    cutoff = utc_now() - timedelta(days=120)

    try:
        rows = db.session.execute(
            select(
                Trade.entry_date,
                Trade.exit_date,
                Trade.created_at,
                Trade.updated_at,
                Trade.post_trade_notes,
                Trade.lessons_learned,
            ).where(
                Trade.user_id == user_id,
                Trade.created_at >= cutoff,
            )
        ).all()
        for entry_date, exit_date, created_at, updated_at, notes, lessons in rows:
            for dt in (entry_date, exit_date, created_at, updated_at):
                d = _to_local_day(dt)
                if d:
                    days.add(d)
            if (notes or '').strip() or (lessons or '').strip():
                d = _to_local_day(updated_at or exit_date or created_at)
                if d:
                    days.add(d)
    except Exception:
        _rollback_quietly()

    try:
        plan_rows = db.session.execute(
            select(
                TradePlan.created_at,
                TradePlan.updated_at,
                TradePlan.reviewed_at,
            ).where(
                TradePlan.user_id == user_id,
                TradePlan.created_at >= cutoff,
            )
        ).all()
        for created_at, updated_at, reviewed_at in plan_rows:
            for dt in (created_at, updated_at, reviewed_at):
                d = _to_local_day(dt)
                if d:
                    days.add(d)
    except Exception:
        _rollback_quietly()

    return days


def get_journaling_streak(user_id: int, tz_name: str = 'UTC') -> int:
    """Consecutive calendar days with journal activity (distinct from P/L streak)."""
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo((tz_name or 'UTC').strip() or 'UTC')
    except Exception:
        tz = timezone.utc

    active = _activity_dates_for_user(user_id, tz_name)
    if not active:
        return 0

    today = datetime.now(tz).date()
    streak = 0
    d = today
    while d in active:
        streak += 1
        d -= timedelta(days=1)
    return streak


def ensure_weekly_performance_score(user_id: int):
    """Calculate this week's score once if missing."""
    today = utc_now().date()
    week_start = today - timedelta(days=today.weekday())
    try:
        existing = PerformanceScore.query.filter_by(user_id=user_id, week_start=week_start).first()
        if existing:
            return existing
        return calculate_weekly_score(user_id, week_start=week_start)
    except Exception:
        _rollback_quietly()
        return None


def setup_letter_grade(win_rate: float, count: int, avg_rr: float) -> Tuple[str, str]:
    """Return (grade, bootstrap color token) for playbook setup cards."""
    if count < 3:
        return '—', 'secondary'
    score = win_rate * 0.55 + min(avg_rr, 3.0) / 3.0 * 35.0 + min(count, 20) / 20.0 * 10.0
    if score >= 82:
        return 'A', 'success'
    if score >= 70:
        return 'B', 'primary'
    if score >= 55:
        return 'C', 'warning'
    return 'D', 'danger'


def get_morning_briefing(user_id: int, user_name: str = '') -> Dict[str, Any]:
    try:
        from app.services.ai_cache import get_cached_morning_briefing

        return get_cached_morning_briefing(user_id, user_name=user_name) or {'lines': [], 'has_data': False}
    except Exception:
        _rollback_quietly()
        return {'lines': [], 'has_data': False}


def get_weekly_review_payload(user_id: int, user_name: str = '') -> Dict[str, Any]:
    analyzer = AIAnalyzer(user_id)
    weekly = {}
    suggested = ''
    try:
        weekly = analyzer.get_weekly_review() or {}
    except Exception:
        _rollback_quietly()
        weekly = {}
    try:
        suggested = analyzer.suggest_weekly_focus_rule()
    except Exception:
        _rollback_quietly()
        suggested = ''
    return {
        'weekly': weekly,
        'suggested_focus': suggested,
        'review_queue': get_review_queue(user_id),
        'user_name': user_name,
    }


def build_dashboard_daily_context(user, *, user_name: str = '') -> Dict[str, Any]:
    """Bundle daily-loop data for dashboard home."""
    uid = user.id
    tz = getattr(user, 'timezone', None) or 'UTC'
    review_queue = get_review_queue(uid)
    weekly_score = ensure_weekly_performance_score(uid)
    briefing = get_morning_briefing(uid, user_name=user_name or getattr(user, 'username', '') or '')
    wf = ''
    try:
        wf = (getattr(user, 'weekly_focus_rule', None) or '').strip()
    except Exception:
        _rollback_quietly()
        wf = ''

    return {
        'review_queue': review_queue,
        'journaling_streak': get_journaling_streak(uid, tz),
        'morning_briefing': briefing,
        'weekly_score': weekly_score,
        'weekly_focus': wf,
    }


def create_sample_trades(user_id: int) -> int:
    """Create a small demo dataset for onboarding (idempotent if trades exist)."""
    try:
        existing = (
            db.session.query(func.count(Trade.id)).filter(Trade.user_id == user_id).scalar() or 0
        )
    except Exception:
        _rollback_quietly()
        existing = 0
    if existing:
        return 0

    now = utc_now()
    samples = [
        dict(symbol='EURUSD', trade_type='BUY', lot_size=0.1, entry_price=1.0850, exit_price=1.0895,
             stop_loss=1.0820, take_profit=1.0920, profit_loss=45.0, risk_reward=1.5,
             emotion='Disciplined', strategy='London breakout',
             post_trade_notes='Waited for confirmation. Good patience.'),
        dict(symbol='XAUUSD', trade_type='SELL', lot_size=0.01, entry_price=2350.0, exit_price=2362.0,
             stop_loss=2365.0, take_profit=2335.0, profit_loss=-12.0, risk_reward=0.8,
             emotion='FOMO', strategy='Gold scalp',
             lessons_learned='Entered before level rejection — need stricter trigger.'),
        dict(symbol='NAS100', trade_type='BUY', lot_size=0.1, entry_price=18200.0, exit_price=18280.0,
             stop_loss=18160.0, take_profit=18320.0, profit_loss=80.0, risk_reward=2.0,
             emotion='Calm & Focused', strategy='NY open momentum',
             post_trade_notes='Followed plan. Held to target.'),
    ]
    created = 0
    try:
        for i, row in enumerate(samples):
            entry = now - timedelta(days=7 - i)
            exit_d = entry + timedelta(hours=4)
            t = Trade(
                user_id=user_id,
                symbol=row['symbol'],
                trade_type=row['trade_type'],
                lot_size=row['lot_size'],
                entry_price=row['entry_price'],
                exit_price=row['exit_price'],
                stop_loss=row['stop_loss'],
                take_profit=row['take_profit'],
                entry_date=entry,
                exit_date=exit_d,
                status='CLOSED',
                profit_loss=row['profit_loss'],
                risk_reward=row['risk_reward'],
                emotion=row['emotion'],
                strategy=row['strategy'],
                post_trade_notes=row.get('post_trade_notes'),
                lessons_learned=row.get('lessons_learned'),
            )
            db.session.add(t)
            created += 1
        db.session.commit()
    except Exception:
        _rollback_quietly()
        return 0
    return created
