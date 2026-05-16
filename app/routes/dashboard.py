"""
Dashboard Routes
Analytics, statistics, and performance overview
"""

from __future__ import annotations

from typing import Optional

from flask import Blueprint, render_template, jsonify, current_app, session
from flask_login import login_required, current_user
from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from app.models.performance_score import PerformanceScore
from app.services.performance_calculator import calculate_weekly_score, get_performance_history
from app.services.pattern_detector import detect_patterns
from app.services.emotion_analyzer import EmotionAnalyzer, analyze_emotions
from app.services.ai_insights import AIAnalyzer
from app.services.web_ai import answer_with_web, OpenAIRateLimited
from sqlalchemy import case, extract, func, or_, update
from app import db
from app.models.user import User
from app.models.ai_coaching_note import AICoachingNote
from flask import request, flash, redirect, url_for
from datetime import datetime, timedelta, timezone
from app.utils.timeutil import utc_now
import random
from app.services.entitlements import _safe_getattr, require_feature
from zoneinfo import ZoneInfo
import os

# Create Blueprint
bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

# ==================== Safe AI Summary Fallback ====================

def _safe_ai_summary():
    """
    Returns a fully-populated fallback AI summary dict.
    Every key that any template references must exist here.
    """
    return {
        'label': 'AI Buddy',
        'period': 'Last 7 days',
        'summary': 'No trade data yet. Log some trades to unlock AI Buddy insights.',
        'stats': {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0.0,
            'total_pnl': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'avg_rr': 0.0,
            'best_trade': None,
            'worst_trade': None,
        },
        'setups': {
            'best_strategy': None,
            'best_instrument': None,
            'best_emotion': None,
            'worst_strategy': None,
            'worst_instrument': None,
            'worst_emotion': None,
        },
        'day_insights': {},
        'alerts': [],
        'strengths': [],
        'weaknesses': [],
        'recommendations': [],
    }


def _safe_monthly_review():
    """Returns a safe monthly review fallback dict."""
    return {
        'label': 'Monthly AI Review',
        'period': 'Last 30 days',
        'stats': {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0.0,
            'total_pnl': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'avg_rr': 0.0,
            'best_trade': None,
            'worst_trade': None,
        },
        'direction': 'needs review',
        'summary': 'No data available for the last 30 days.',
    }


def _safe_behavioral_insights():
    """Returns a safe behavioral insights fallback dict."""
    return {
        'discipline_score': 0.0,
        'consistency_score': 0.0,
        'emotional_bias': 'No data',
        'confidence_trend': None,
        'risk_behavior': {
            'avg_rr': 0.0,
            'high_risk_trades': 0,
        },
    }


# ==================== Main Dashboard ====================

@bp.route('/')
@login_required
def index():
    """
    Main Dashboard

    Overview of trading performance with key metrics and charts
    """
    # Get user statistics
    stats = current_user.get_stats()

    # Get recent trades
    recent_trades = current_user.get_recent_trades(limit=5)

    # Get current streak
    streak = current_user.get_current_streak()

    from app.content.motivational_quotes import MOTIVATIONAL_QUOTES

    initial_mq = random.choice(MOTIVATIONAL_QUOTES) if MOTIVATIONAL_QUOTES else {
        'text': 'Trade with discipline.',
        'author': 'TradeVerse',
    }

    # Calculate additional metrics
    total_trades = stats['total_trades']

    # Calculate max drawdown
    max_drawdown = calculate_max_drawdown()

    # Get this week's performance
    week_performance = get_week_performance()

    # AI Buddy snapshot — wrapped in try/except so a broken AI service never
    # takes down the main dashboard.
    try:
        ai_summary = AIAnalyzer(current_user.id).get_weekly_review()
        # Ensure every key the template touches actually exists
        ai_summary.setdefault('summary', '')
        ai_summary.setdefault('setups', {})
        ai_summary['setups'].setdefault('best_strategy', None)
        ai_summary['setups'].setdefault('worst_strategy', None)
        ai_summary['setups'].setdefault('best_instrument', None)
        ai_summary['setups'].setdefault('best_emotion', None)
        ai_summary.setdefault('weaknesses', [])
        ai_summary.setdefault('recommendations', [])
        ai_summary.setdefault('alerts', [])
        ai_summary.setdefault('strengths', [])
        ai_summary.setdefault('stats', _safe_ai_summary()['stats'])
        ai_summary.setdefault('day_insights', {})
    except Exception as exc:
        current_app.logger.warning('AI Buddy weekly review failed: %s', exc)
        ai_summary = _safe_ai_summary()

    # Get best and worst trades
    best_trade = Trade.query.filter_by(
        user_id=current_user.id,
        status='CLOSED'
    ).order_by(Trade.profit_loss.desc()).first()

    worst_trade = Trade.query.filter_by(
        user_id=current_user.id,
        status='CLOSED'
    ).order_by(Trade.profit_loss).first()

    plan_exists = db.session.query(TradePlan.id).filter_by(user_id=current_user.id).limit(1).scalar()
    review_exists = db.session.query(Trade.id).filter(
        Trade.user_id == current_user.id,
        Trade.status == 'CLOSED',
        or_(Trade.post_trade_notes.isnot(None), Trade.lessons_learned.isnot(None)),
    ).limit(1).scalar()

    wf = ''
    try:
        wf = (_safe_getattr(current_user, 'weekly_focus_rule', None) or '').strip()
    except Exception:
        wf = ''

    onboarding = {
        'has_plan': bool(plan_exists),
        'has_trade': stats['total_trades'] > 0,
        'has_review': bool(review_exists),
        'analytics_done': bool(session.get('onboarding_analytics_visited')),
        'weekly_focus_set': bool(wf),
    }

    pinned_note = None
    try:
        pinned_note = (
            AICoachingNote.query.filter(
                AICoachingNote.user_id == current_user.id,
                AICoachingNote.is_active == True,
            )
            .order_by(AICoachingNote.updated_at.desc().nullslast(), AICoachingNote.created_at.desc())
            .first()
        )
    except Exception:
        pinned_note = None

    return render_template('dashboard/index.html',
                           stats=stats,
                           recent_trades=recent_trades,
                           streak=streak,
                           initial_quote_text=initial_mq['text'],
                           initial_quote_author=initial_mq.get('author', 'TradeVerse'),
                           max_drawdown=max_drawdown,
                           week_performance=week_performance,
                           ai_summary=ai_summary,
                           best_trade=best_trade,
                           worst_trade=worst_trade,
                           onboarding=onboarding,
                           pinned_note=pinned_note)

# ==================== Analytics ====================

@bp.route('/analytics')
@login_required
def analytics():
    """
    Detailed Analytics

    In-depth analysis of trading performance
    """
    session['onboarding_analytics_visited'] = True

    # Performance by instrument
    instrument_stats = db.session.query(
        Trade.symbol,
        func.count(Trade.id).label('count'),
        func.sum(Trade.profit_loss).label('total_pnl'),
        func.avg(Trade.profit_loss).label('avg_pnl')
    ).filter(
        Trade.user_id == current_user.id,
        Trade.status == 'CLOSED',
        Trade.profit_loss.isnot(None)
    ).group_by(Trade.symbol).all()

    # Performance by strategy
    strategy_stats = db.session.query(
        Trade.strategy,
        func.count(Trade.id).label('count'),
        func.sum(Trade.profit_loss).label('total_pnl'),
        func.avg(Trade.profit_loss).label('avg_pnl')
    ).filter(
        Trade.user_id == current_user.id,
        Trade.status == 'CLOSED',
        Trade.strategy.isnot(None),
        Trade.profit_loss.isnot(None)
    ).group_by(Trade.strategy).all()

    # Performance by emotion
    emotion_stats = db.session.query(
        Trade.emotion,
        func.count(Trade.id).label('count'),
        func.sum(Trade.profit_loss).label('total_pnl')
    ).filter(
        Trade.user_id == current_user.id,
        Trade.status == 'CLOSED',
        Trade.emotion.isnot(None),
        Trade.profit_loss.isnot(None)
    ).group_by(Trade.emotion).all()

    # Performance by session
    session_stats = db.session.query(
        Trade.session_type,
        func.count(Trade.id).label('count'),
        func.sum(Trade.profit_loss).label('total_pnl')
    ).filter(
        Trade.user_id == current_user.id,
        Trade.status == 'CLOSED',
        Trade.session_type.isnot(None),
        Trade.profit_loss.isnot(None)
    ).group_by(Trade.session_type).all()

    # Performance by day of week
    day_stats = get_performance_by_day()

    return render_template('dashboard/analytics.html',
                           instrument_stats=instrument_stats,
                           strategy_stats=strategy_stats,
                           emotion_stats=emotion_stats,
                           session_stats=session_stats,
                           day_stats=day_stats)


@bp.route('/api/advanced-metrics')
@login_required
@require_feature('advanced_analytics')
def advanced_metrics_api():
    """
    Trader-grade metrics: R distribution, expectancy (R), max drawdown abs/rel,
    grouped performance by emotion/session/strategy.
    """
    from app.services.analytics_engine import equity_curve_points, expectancy_r, max_drawdown, group_pnl
    from sqlalchemy.orm import load_only

    trades = (
        Trade.query.filter(
            Trade.user_id == current_user.id,
            Trade.status == 'CLOSED',
            Trade.profit_loss.isnot(None),
            Trade.exit_date.isnot(None),
        )
        .options(
            load_only(
                Trade.id,
                Trade.profit_loss,
                Trade.exit_date,
                Trade.risk_amount,
                Trade.stop_loss,
                Trade.entry_price,
                Trade.lot_size,
                Trade.emotion,
                Trade.session_type,
                Trade.strategy,
            )
        )
        .order_by(Trade.exit_date)
        .all()
    )

    points = equity_curve_points(trades)
    dd = max_drawdown(points)
    exp = expectancy_r(points)

    by_emotion = group_pnl(trades, lambda t: getattr(t, "emotion", None))
    by_session = group_pnl(trades, lambda t: getattr(t, "session_type", None))
    by_strategy = group_pnl(trades, lambda t: getattr(t, "strategy", None))

    r_values = [p.r for p in points if p.r is not None]
    r_values.sort()

    return jsonify(
        {
            "count_closed": len(trades),
            "expectancy_r": round(exp["expectancy_r"], 4),
            "avg_r": round(exp["avg_r"], 4),
            "win_rate_r": round(exp["win_rate"] * 100, 2),
            "max_drawdown_abs": round(dd["max_drawdown_abs"], 2),
            "max_drawdown_rel": round(dd["max_drawdown_rel"] * 100, 2),
            "r_values": [round(float(r), 4) for r in r_values[-500:]],  # cap payload
            "by_emotion": by_emotion[:25],
            "by_session": by_session[:25],
            "by_strategy": by_strategy[:25],
        }
    )


@bp.route('/api/stats')
@login_required
def stats_api():
    """
    Returns user's current statistics as JSON for live UI updates
    """
    stats = current_user.get_stats()

    # Use user's timezone for day/week windows; convert boundaries to naive UTC
    # because DB datetimes are stored as naive UTC across the app.
    tz_name = (getattr(current_user, "timezone", None) or "UTC").strip()
    try:
        user_tz = ZoneInfo(tz_name)
    except Exception:
        user_tz = ZoneInfo("UTC")

    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(user_tz)
    start_today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_tomorrow_local = start_today_local + timedelta(days=1)

    start_today = start_today_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_today = start_tomorrow_local.astimezone(timezone.utc).replace(tzinfo=None)
    start_7d = (now_utc - timedelta(days=7)).replace(tzinfo=None)

    q_closed = Trade.query.filter(
        Trade.user_id == current_user.id,
        Trade.status == "CLOSED",
        Trade.profit_loss.isnot(None),
        Trade.exit_date.isnot(None),
    )

    def _window_agg(start_dt):
        pnl, wins, losses, avg_rr = (
            db.session.query(
                func.coalesce(func.sum(Trade.profit_loss), 0.0),
                func.coalesce(func.sum(case((Trade.profit_loss > 0, 1), else_=0)), 0),
                func.coalesce(func.sum(case((Trade.profit_loss < 0, 1), else_=0)), 0),
                func.coalesce(func.avg(Trade.risk_reward), 0.0),
            )
            .filter(q_closed.where(Trade.exit_date >= start_dt).whereclause)
            .one()
        )
        wins_i = int(wins or 0)
        losses_i = int(losses or 0)
        denom = wins_i + losses_i
        win_rate = (wins_i / denom) * 100.0 if denom else 0.0
        return float(pnl or 0.0), wins_i, losses_i, float(avg_rr or 0.0), float(win_rate)

    # Today's window: [start_today, end_today)
    pnl_today, wins_today, losses_today, avg_rr_today = (
        db.session.query(
            func.coalesce(func.sum(Trade.profit_loss), 0.0),
            func.coalesce(func.sum(case((Trade.profit_loss > 0, 1), else_=0)), 0),
            func.coalesce(func.sum(case((Trade.profit_loss < 0, 1), else_=0)), 0),
            func.coalesce(func.avg(Trade.risk_reward), 0.0),
        )
        .filter(
            q_closed.where(Trade.exit_date >= start_today).whereclause,
            Trade.exit_date < end_today,
        )
        .one()
    )
    wins_today = int(wins_today or 0)
    losses_today = int(losses_today or 0)
    denom_today = wins_today + losses_today
    win_rate_today = (wins_today / denom_today) * 100.0 if denom_today else 0.0
    pnl_today = float(pnl_today or 0.0)
    avg_rr_today = float(avg_rr_today or 0.0)

    pnl_7d, wins_7d, losses_7d, avg_rr_7d, win_rate_7d = _window_agg(start_7d)

    trades_today = Trade.query.filter(
        Trade.user_id == current_user.id,
        Trade.entry_date >= start_today,
        Trade.entry_date < end_today,
    ).with_entities(Trade.id).count()
    # Ensure numeric fields are serializable
    safe = {
        'total_trades': stats.get('total_trades', 0),
        'open_trades': stats.get('open_trades', 0),
        'closed_trades': stats.get('closed_trades', 0),
        'winning_trades': stats.get('winning_trades', 0),
        'losing_trades': stats.get('losing_trades', 0),
        'win_rate': float(stats.get('win_rate', 0.0)),
        'total_pnl': float(stats.get('total_pnl', 0.0)),
        'avg_rr': float(stats.get('avg_rr', 0.0)),
        'trades_today': int(trades_today or 0),
        'pnl_today': float(pnl_today),
        'win_rate_today': float(win_rate_today),
        'avg_rr_today': float(avg_rr_today),
        'pnl_7d': float(pnl_7d),
        'win_rate_7d': float(win_rate_7d),
        'avg_rr_7d': float(avg_rr_7d),
        'wins_7d': int(wins_7d),
        'losses_7d': int(losses_7d),
    }
    return jsonify(safe)

# ==================== Calendar View ====================

@bp.route('/calendar')
@login_required
def calendar():
    """
    Calendar View

    Visual calendar showing trading activity
    """
    from calendar import monthrange, Calendar, SUNDAY

    def _safe_int_arg(name, default, *, lo=None, hi=None):
        raw = request.args.get(name, default=None, type=str)
        if raw is None or str(raw).strip() == "":
            v = default
        else:
            try:
                v = int(str(raw).strip(), 10)
            except ValueError:
                v = default
        if lo is not None and v < lo:
            v = default
        if hi is not None and v > hi:
            v = default
        return v

    year = _safe_int_arg("year", datetime.now().year, lo=1990, hi=2200)
    month = _safe_int_arg("month", datetime.now().month, lo=1, hi=12)

    # Validate year range (reasonable bounds)
    if year < 2000:
        year = 2000
    elif year > 2100:
        year = 2100

    # Handle month overflow
    if month > 12:
        month = 1
        year += 1
    elif month < 1:
        month = 12
        year -= 1

    days_in_month = monthrange(year, month)[1]

    # Sunday-first weeks (matches UI); 0 = padding cell outside this month
    _cal = Calendar(firstweekday=SUNDAY)
    calendar_weeks = [
        [d.day if d.month == month else 0 for d in week]
        for week in _cal.monthdatescalendar(year, month)
    ]
    today = datetime.now()
    today_day = today.day if (today.year == year and today.month == month) else None

    # Get trades for the month
    trades = Trade.query.filter(
        Trade.user_id == current_user.id,
        extract('year', Trade.entry_date) == year,
        extract('month', Trade.entry_date) == month
    ).all()

    # Organize by day
    trades_by_day = {}
    for trade in trades:
        day = trade.entry_date.day
        if day not in trades_by_day:
            trades_by_day[day] = []
        trades_by_day[day].append(trade)

    # Calculate daily P/L
    daily_pnl = {}
    for day, day_trades in trades_by_day.items():
        pnl = sum(t.profit_loss for t in day_trades if t.profit_loss)
        daily_pnl[day] = pnl

    return render_template(
        'dashboard/calendar.html',
        year=year,
        month=month,
        days_in_month=days_in_month,
        calendar_weeks=calendar_weeks,
        today_day=today_day,
        trades_by_day=trades_by_day,
        daily_pnl=daily_pnl,
    )

# ==================== API Endpoints for Charts ====================

@bp.route('/api/equity-curve')
@login_required
def equity_curve_api():
    """
    Equity Curve Data

    Returns data for equity curve chart
    """
    max_points = request.args.get('max_points', 500, type=int)
    trades = Trade.query.filter_by(
        user_id=current_user.id,
        status='CLOSED'
    ).order_by(Trade.exit_date).all()

    equity_data = []
    cumulative_pnl = 0

    for trade in trades:
        if trade.profit_loss and trade.exit_date:
            cumulative_pnl += trade.profit_loss
            equity_data.append({
                'date': trade.exit_date.strftime('%Y-%m-%d'),
                'equity': round(cumulative_pnl, 2),
                'trade_pnl': round(trade.profit_loss, 2)
            })

    # Downsample for chart responsiveness
    if max_points and len(equity_data) > max_points:
        from app.utils.downsample import downsample_minmax

        equity_data = downsample_minmax(equity_data, x_key="date", y_key="equity", max_points=max_points)

    return jsonify(equity_data)

@bp.route('/api/win-rate-chart')
@login_required
def win_rate_chart_api():
    """
    Win Rate Chart Data

    Returns win/loss distribution for pie chart
    """
    stats = current_user.get_stats()

    return jsonify({
        'wins': stats['winning_trades'],
        'losses': stats['losing_trades']
    })

@bp.route('/api/monthly-performance')
@login_required
def monthly_performance_api():
    """
    Monthly Performance Data

    Returns P/L by month for bar chart
    """
    # Get trades from last 12 months
    trades = Trade.query.filter(
        Trade.user_id == current_user.id,
        Trade.status == 'CLOSED',
        Trade.profit_loss.isnot(None),
        Trade.exit_date >= utc_now() - timedelta(days=365)
    ).all()

    # Group by month (user timezone)
    try:
        user_tz = ZoneInfo((getattr(current_user, 'timezone', None) or 'UTC').strip() or 'UTC')
    except Exception:
        user_tz = ZoneInfo('UTC')

    monthly_data = {}
    for trade in trades:
        if trade.exit_date:
            local_exit = trade.exit_date.replace(tzinfo=timezone.utc).astimezone(user_tz)
            month_key = local_exit.strftime('%Y-%m')
            if month_key not in monthly_data:
                monthly_data[month_key] = 0
            monthly_data[month_key] += trade.profit_loss

    # Format for chart
    result = [
        {
            'month': month,
            'pnl': round(pnl, 2)
        }
        for month, pnl in sorted(monthly_data.items())
    ]

    return jsonify(result)

# ==================== Helper Functions ====================

def calculate_max_drawdown():
    """Calculate maximum drawdown"""
    trades = Trade.query.filter_by(
        user_id=current_user.id,
        status='CLOSED'
    ).order_by(Trade.exit_date).all()

    if not trades:
        return 0

    equity = 0
    peak = 0
    max_dd = 0

    for trade in trades:
        if trade.profit_loss:
            equity += trade.profit_loss
            if equity > peak:
                peak = equity
            drawdown = peak - equity
            if drawdown > max_dd:
                max_dd = drawdown

    return max_dd

def get_week_performance():
    """Get performance for last 7 days (user timezone)."""
    try:
        user_tz = ZoneInfo((getattr(current_user, 'timezone', None) or 'UTC').strip() or 'UTC')
    except Exception:
        user_tz = ZoneInfo('UTC')

    now_local = datetime.now(user_tz)
    start_local = now_local - timedelta(days=7)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)

    trades = Trade.query.filter(
        Trade.user_id == current_user.id,
        Trade.status == 'CLOSED',
        Trade.exit_date >= start_utc
    ).all()

    total_pnl = sum((t.profit_loss or 0) for t in trades if t.profit_loss is not None)
    total_trades = len(trades)
    wins = len([t for t in trades if (t.profit_loss is not None) and t.profit_loss > 0])

    return {
        'pnl': total_pnl,
        'trades': total_trades,
        'wins': wins,
        'win_rate': (wins / total_trades * 100) if total_trades > 0 else 0
    }

def get_performance_by_day():
    """Get performance by day of week (user timezone)."""
    from calendar import day_name

    trades = Trade.query.filter_by(
        user_id=current_user.id,
        status='CLOSED'
    ).all()

    day_stats = {i: {'wins': 0, 'losses': 0, 'pnl': 0} for i in range(7)}

    try:
        user_tz = ZoneInfo((getattr(current_user, 'timezone', None) or 'UTC').strip() or 'UTC')
    except Exception:
        user_tz = ZoneInfo('UTC')

    for trade in trades:
        if trade.exit_date and trade.profit_loss is not None:
            # exit_date is stored as naive UTC; interpret as UTC then convert to user TZ
            local_exit = trade.exit_date.replace(tzinfo=timezone.utc).astimezone(user_tz)
            day = local_exit.weekday()
            if trade.profit_loss > 0:
                day_stats[day]['wins'] += 1
            else:
                day_stats[day]['losses'] += 1
            day_stats[day]['pnl'] += trade.profit_loss

    result = []
    for day in range(7):
        total = day_stats[day]['wins'] + day_stats[day]['losses']
        win_rate = (day_stats[day]['wins'] / total * 100) if total > 0 else 0
        result.append({
            'day': day_name[day],
            'win_rate': round(win_rate, 1),
            'total_trades': total,
            'pnl': round(day_stats[day]['pnl'], 2)
        })

    return result


# ==================== Performance Score ====================

@bp.route('/performance')
@login_required
def performance():
    """
    Performance Score Dashboard

    Weekly performance scores with progress charts
    """
    # Get current week's score
    today = utc_now().date()
    week_start = today - timedelta(days=today.weekday())

    current_score = PerformanceScore.query.filter_by(
        user_id=current_user.id,
        week_start=week_start
    ).first()

    # Get score history (last 12 weeks)
    score_history = get_performance_history(current_user.id, weeks=12)

    # Calculate improvement trend
    if len(score_history) >= 2:
        recent_avg = sum(s.overall_score for s in score_history[:4]) / min(4, len(score_history))
        older_avg = sum(s.overall_score for s in score_history[4:8]) / max(1, min(4, len(score_history) - 4))
        trend = recent_avg - older_avg
    else:
        trend = 0

    return render_template('dashboard/performance.html',
                           current_score=current_score,
                           score_history=score_history,
                           trend=trend)


@bp.route('/performance/calculate', methods=['POST'])
@login_required
def calculate_performance():
    """Calculate/recalculate current week's performance score"""
    try:
        score = calculate_weekly_score(current_user.id)
        flash(f'✅ Performance score calculated: {score.overall_score:.1f} ({score.grade})', 'success')
    except Exception as e:
        flash(f'❌ Error calculating score: {str(e)}', 'danger')

    return redirect(url_for('dashboard.performance'))


@bp.route('/api/performance-history')
@login_required
def performance_history_api():
    """
    Performance History API

    Returns performance score history for charts
    """
    scores = get_performance_history(current_user.id, weeks=12)

    return jsonify([s.to_dict() for s in reversed(scores)])


# ==================== AI Buddy Dashboard ====================

def _safe_same_site_redirect(target: Optional[str]):
    """Allow only same-app relative paths (blocks open redirects)."""
    t = (target or '').strip()
    if not t:
        return url_for('dashboard.index')
    if t.startswith('/') and not t.startswith('//'):
        return t
    return url_for('dashboard.index')


@bp.route('/onboarding/weekly-focus', methods=['POST'])
@login_required
def save_weekly_focus():
    """Persist user's weekly trading rule for AI Buddy coaching."""
    text = (request.form.get('weekly_focus') or '').strip()
    if len(text) > 4000:
        text = text[:4000]
    next_url = _safe_same_site_redirect(request.form.get('next'))
    try:
        # Core UPDATE avoids deferred / load_only login edge cases on current_user.
        db.session.execute(
            update(User)
            .where(User.id == current_user.id)
            .values(weekly_focus_rule=text if text else None)
        )
        db.session.commit()
        flash('Weekly focus saved. AI Buddy will use this as context.', 'success')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning('save_weekly_focus failed: %s', exc)
        flash(
            'Could not save weekly focus. Run `flask db upgrade` if the database is missing the latest migrations.',
            'danger',
        )
    return redirect(next_url)


@bp.route('/ai')
@login_required
def ai():
    """
    AI Buddy Dashboard

    Premium AI insights built from your real trading history.
    """
    if not current_app.config.get('FEATURE_AI_BUDDY', True):
        flash('AI Buddy is temporarily unavailable.', 'warning')
        return redirect(url_for('dashboard.index'))

    analyzer = AIAnalyzer(current_user.id)

    # Wrap every AI call so a data error never produces a 500
    try:
        weekly_review = analyzer.get_weekly_review()
        weekly_review.setdefault('summary', '')
        weekly_review.setdefault('stats', _safe_ai_summary()['stats'])
        weekly_review.setdefault('setups', {})
        weekly_review['setups'].setdefault('best_strategy', None)
        weekly_review['setups'].setdefault('worst_strategy', None)
        weekly_review['setups'].setdefault('best_instrument', None)
        weekly_review['setups'].setdefault('best_emotion', None)
        weekly_review.setdefault('day_insights', {})
        weekly_review.setdefault('alerts', [])
        weekly_review.setdefault('strengths', [])
        weekly_review.setdefault('weaknesses', [])
        weekly_review.setdefault('recommendations', [])
    except Exception as exc:
        current_app.logger.warning('AI Buddy get_weekly_review failed: %s', exc)
        weekly_review = _safe_ai_summary()

    try:
        monthly_review = analyzer.get_monthly_review()
        monthly_review.setdefault('stats', _safe_monthly_review()['stats'])
        monthly_review.setdefault('summary', '')
        monthly_review.setdefault('direction', 'needs review')
    except Exception as exc:
        current_app.logger.warning('AI Buddy get_monthly_review failed: %s', exc)
        monthly_review = _safe_monthly_review()

    try:
        behavioral_insights = analyzer.get_behavioral_insights()
        behavioral_insights.setdefault('discipline_score', 0.0)
        behavioral_insights.setdefault('consistency_score', 0.0)
        behavioral_insights.setdefault('emotional_bias', 'No data')
        behavioral_insights.setdefault('confidence_trend', None)
        behavioral_insights.setdefault('risk_behavior', {'avg_rr': 0.0, 'high_risk_trades': 0})
    except Exception as exc:
        current_app.logger.warning('AI Buddy get_behavioral_insights failed: %s', exc)
        behavioral_insights = _safe_behavioral_insights()

    try:
        voice_review = analyzer.get_voice_review(user_name=(current_user.username or ''))
        voice_summary = (voice_review.get('text') if isinstance(voice_review, dict) else '') or ''
        if not isinstance(voice_summary, str):
            voice_summary = ''
        # Strip characters that would break the inline JS string
        voice_summary = voice_summary.replace('"', "'").replace('\n', ' ').replace('\r', '')
    except Exception as exc:
        current_app.logger.warning('AI Buddy get_voice_summary failed: %s', exc)
        voice_summary = 'AI Buddy has no data to summarise yet. Log some trades to get started.'

    alerts = weekly_review.get('alerts', [])

    wf = ''
    try:
        wf = (_safe_getattr(current_user, 'weekly_focus_rule', None) or '').strip()
    except Exception:
        wf = ''

    pinned_note = None
    try:
        pinned_note = (
            AICoachingNote.query.filter(
                AICoachingNote.user_id == current_user.id,
                AICoachingNote.is_active == True,
            )
            .order_by(AICoachingNote.updated_at.desc().nullslast(), AICoachingNote.created_at.desc())
            .first()
        )
    except Exception:
        pinned_note = None

    return render_template('dashboard/ai.html',
                           weekly_review=weekly_review,
                           monthly_review=monthly_review,
                           behavioral_insights=behavioral_insights,
                           voice_summary=voice_summary,
                           alerts=alerts,
                           weekly_focus_rule=wf,
                           pinned_note=pinned_note)


@bp.route('/ai/notes/save', methods=['POST'])
@login_required
def save_ai_note():
    """Save (or replace) the user's pinned coaching note."""
    rule = (request.form.get("pinned_rule") or "").strip()
    checklist = (request.form.get("checklist_text") or "").strip()
    source = (request.form.get("source") or "manual").strip()[:30] or "manual"
    next_url = _safe_same_site_redirect(request.form.get("next"))

    if len(rule) > 4000:
        rule = rule[:4000]
    if len(checklist) > 8000:
        checklist = checklist[:8000]

    try:
        # Only one active pinned note per user
        AICoachingNote.query.filter(
            AICoachingNote.user_id == current_user.id,
            AICoachingNote.is_active == True,
        ).update({"is_active": False})

        note = AICoachingNote(
            user_id=current_user.id,
            pinned_rule=rule,
            checklist_text=checklist,
            source=source,
            is_active=True,
        )
        db.session.add(note)
        db.session.commit()
        flash("Saved. Your coaching note is pinned on your dashboard.", "success")
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning("save_ai_note failed: %s", exc)
        flash("Could not save coaching note right now.", "danger")

    return redirect(next_url)


@bp.route('/ai/notes/clear', methods=['POST'])
@login_required
def clear_ai_note():
    """Unpin/clear the active coaching note."""
    next_url = _safe_same_site_redirect(request.form.get("next"))
    try:
        AICoachingNote.query.filter(
            AICoachingNote.user_id == current_user.id,
            AICoachingNote.is_active == True,
        ).update({"is_active": False})
        db.session.commit()
        flash("Pinned coaching note cleared.", "info")
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning("clear_ai_note failed: %s", exc)
        flash("Could not clear the coaching note right now.", "danger")
    return redirect(next_url)


@bp.route('/ai/query', methods=['POST'])
@login_required
def ai_query():
    """Ask AI Buddy about your trading performance."""
    if not current_app.config.get('FEATURE_AI_BUDDY', True):
        return jsonify({'answer': 'AI Buddy is temporarily unavailable.', 'follow_ups': []}), 503

    payload = request.get_json() or {}
    question = payload.get('question', '').strip()
    if not question:
        return jsonify(
            {
                "answer": "Ask me anything about your recent performance or about trading in general.",
                "follow_ups": [
                    "What’s my biggest performance leak this week?",
                    "What should my one rule be next week?",
                    "Explain risk:reward and how to improve it.",
                ],
            }
        )
    if len(question) > 1200:
        return jsonify({"answer": "That question is a bit long. Please shorten it and ask again.", "follow_ups": []}), 400
    try:
        history = payload.get('history') or []
        if not isinstance(history, list):
            history = []

        # Prefer local coach for reliability; if web mode is enabled but fails,
        # gracefully fall back to local instead of returning a generic error.
        answer = ""
        follow_ups: list[str] = []
        use_web = bool(current_app.config.get("FEATURE_AI_WEB")) and bool(os.environ.get("OPENAI_API_KEY")) and bool(os.environ.get("TAVILY_API_KEY"))

        # Compact user context so answers stay consistent with your data.
        try:
            wf = (_safe_getattr(current_user, 'weekly_focus_rule', None) or '').strip()
        except Exception:
            wf = ''
        try:
            weekly = AIAnalyzer(current_user.id).get_weekly_review() or {}
            ws = (weekly.get("stats") or {}) if isinstance(weekly, dict) else {}
            ctx_week = (
                f"trades_7d={int(ws.get('total_trades') or 0)}\n"
                f"win_rate_7d={float(ws.get('win_rate') or 0.0):.1f}%\n"
                f"pnl_7d={float(ws.get('total_pnl') or 0.0):.2f}\n"
                f"avg_rr_7d={float(ws.get('avg_rr') or 0.0):.2f}\n"
            )
        except Exception:
            ctx_week = ""
        try:
            s = current_user.get_stats()
            ctx_all = (
                f"open_trades={int(s.get('open_trades') or 0)}\n"
                f"closed_trades_total={int(s.get('closed_trades') or 0)}\n"
                f"win_rate_all_time={float(s.get('win_rate') or 0.0):.1f}%\n"
                f"avg_rr_all_time={float(s.get('avg_rr') or 0.0):.2f}\n"
            )
        except Exception:
            ctx_all = ""
        ctx = (
            f"username={current_user.username or ''}\n"
            + (f"weekly_focus_rule={wf}\n" if wf else "")
            + ctx_week
            + ctx_all
        )
        if use_web:
            try:
                web = answer_with_web(question=question, user_context=ctx, history=history[-12:])
                answer = web.answer
                follow_ups = [str(x) for x in (web.follow_ups or []) if x]
            except OpenAIRateLimited:
                current_app.logger.info(
                    "Web AI: OpenAI rate limited after retries; using local coach."
                )
            except Exception:
                current_app.logger.warning(
                    "Web AI failed; falling back to local coach", exc_info=True
                )

        if not answer:
            result = AIAnalyzer(current_user.id).answer_question(
                question,
                history=history[-12:],
                user_name=(current_user.username or '')
            )
            answer = (result.get('answer') if isinstance(result, dict) else '') or ''
            follow_ups = [str(x) for x in ((result.get('follow_ups') if isinstance(result, dict) else []) or []) if x]

        follow_ups = follow_ups[:3]
        if not follow_ups:
            follow_ups = [
                "What’s my biggest performance leak this week?",
                "What should my one rule be next week?",
                "What should I focus on tomorrow?",
            ]
    except Exception as exc:
        current_app.logger.warning('AI Buddy answer_question failed: %s', exc)
        answer = 'AI Buddy could not process your question right now. Please try again later.'
        follow_ups = []
        wf = ''
    return jsonify({'answer': answer, 'follow_ups': follow_ups, 'context': {'weekly_focus_rule': wf}})


@bp.route('/ai/trade-doctor')
@login_required
def trade_doctor_api():
    """Premium: Diagnose the #1 leak from the last 10 closed trades."""
    try:
        result = AIAnalyzer(current_user.id).trade_doctor(last_n=10)
        if not isinstance(result, dict):
            return jsonify({"text": "Trade Doctor is unavailable right now."}), 200
        return jsonify(result)
    except Exception as exc:
        current_app.logger.warning("trade_doctor_api failed: %s", exc)
        return jsonify({"text": "Trade Doctor could not analyze your trades right now."}), 200


# ==================== Behavior Patterns ====================

@bp.route('/patterns')
@login_required
def patterns():
    """
    Behavior Pattern Analysis

    Displays detected trading patterns and insights
    """
    days = request.args.get('days', 90, type=int)

    # Detect patterns
    detected_patterns = detect_patterns(current_user.id, days=days)

    # Categorize patterns
    positive_patterns = [p for p in detected_patterns if p['type'] == 'positive']
    warning_patterns = [p for p in detected_patterns if p['type'] == 'warning']
    insight_patterns = [p for p in detected_patterns if p['type'] == 'insight']

    # Get trade count for context
    trade_count = Trade.query.filter(
        Trade.user_id == current_user.id,
        Trade.status == 'CLOSED',
        Trade.entry_date >= utc_now() - timedelta(days=days)
    ).with_entities(Trade.id).count()

    return render_template('dashboard/patterns.html',
                           patterns=detected_patterns,
                           positive_patterns=positive_patterns,
                           warning_patterns=warning_patterns,
                           insight_patterns=insight_patterns,
                           trade_count=trade_count,
                           days=days)


# ==================== Emotion Tracking ====================

@bp.route('/emotions')
@login_required
def emotions():
    """
    Emotion Tracking Dashboard

    Visual charts showing emotional trading patterns
    """
    days = request.args.get('days', 90, type=int)

    analyzer = EmotionAnalyzer(current_user.id)

    # Get all emotion data
    performance = analyzer.get_emotion_performance(days)
    profitable = analyzer.get_most_profitable_emotions(days)
    dangerous = analyzer.get_most_dangerous_emotions(days)
    frequency = analyzer.get_emotion_frequency(days)
    summary = analyzer.get_summary(days)
    before_after = analyzer.get_before_after_comparison(days)

    return render_template('dashboard/emotions.html',
                           performance=performance,
                           profitable=profitable,
                           dangerous=dangerous,
                           frequency=frequency,
                           summary=summary,
                           before_after=before_after,
                           days=days)


@bp.route('/api/emotion-chart-data')
@login_required
def emotion_chart_data():
    """API endpoint for emotion chart data"""
    days = request.args.get('days', 90, type=int)

    analyzer = EmotionAnalyzer(current_user.id)
    chart_data = analyzer.get_chart_data(days)

    return jsonify(chart_data)


@bp.route('/api/emotion-trend')
@login_required
def emotion_trend_data():
    """API endpoint for emotion trend over time"""
    days = request.args.get('days', 90, type=int)

    analyzer = EmotionAnalyzer(current_user.id)
    trend_data = analyzer.get_emotion_trend(days)

    return jsonify(trend_data)