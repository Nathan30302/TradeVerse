"""
Dashboard Routes
Analytics, statistics, and performance overview
"""

from flask import Blueprint, render_template, jsonify, current_app
from flask_login import login_required, current_user
from app.models.trade import Trade
from app.models.performance_score import PerformanceScore
from app.services.performance_calculator import calculate_weekly_score, get_performance_history
from app.services.pattern_detector import detect_patterns
from app.services.emotion_analyzer import EmotionAnalyzer, analyze_emotions
from sqlalchemy import func, extract
from app import db
from flask import request, flash, redirect, url_for
from datetime import datetime, timedelta
import random

# Create Blueprint
bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

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
    
    # Get motivational quote
    quote = random.choice(current_app.config.get('QUOTES', []))
    
    # Calculate additional metrics
    total_trades = stats['total_trades']
    
    # Calculate max drawdown
    max_drawdown = calculate_max_drawdown()
    
    # Get this week's performance
    week_performance = get_week_performance()
    
    # Get best and worst trades
    best_trade = Trade.query.filter_by(
        user_id=current_user.id,
        status='CLOSED'
    ).order_by(Trade.profit_loss.desc()).first()
    
    worst_trade = Trade.query.filter_by(
        user_id=current_user.id,
        status='CLOSED'
    ).order_by(Trade.profit_loss).first()
    
    return render_template('dashboard/index.html',
                         stats=stats,
                         recent_trades=recent_trades,
                         streak=streak,
                         quote=quote,
                         max_drawdown=max_drawdown,
                         week_performance=week_performance,
                         best_trade=best_trade,
                         worst_trade=worst_trade)

# ==================== Analytics ====================

@bp.route('/analytics')
@login_required
def analytics():
    """
    Detailed Analytics
    
    In-depth analysis of trading performance
    """
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

# ==================== Calendar View ====================

@bp.route('/calendar')
@login_required
def calendar():
    """
    Calendar View
    
    Visual calendar showing trading activity
    """
    from calendar import monthrange
    
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
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
    
    # Get number of days in month
    days_in_month = monthrange(year, month)[1]
    
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
    
    return render_template('dashboard/calendar.html',
                         year=year,
                         month=month,
                         days_in_month=days_in_month,
                         trades_by_day=trades_by_day,
                         daily_pnl=daily_pnl)

# ==================== API Endpoints for Charts ====================

@bp.route('/api/equity-curve')
@login_required
def equity_curve_api():
    """
    Equity Curve Data
    
    Returns data for equity curve chart
    """
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
        Trade.exit_date >= datetime.now() - timedelta(days=365)
    ).all()
    
    # Group by month
    monthly_data = {}
    for trade in trades:
        if trade.exit_date:
            month_key = trade.exit_date.strftime('%Y-%m')
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
    """Get performance for current week"""
    week_ago = datetime.now() - timedelta(days=7)
    
    trades = Trade.query.filter(
        Trade.user_id == current_user.id,
        Trade.status == 'CLOSED',
        Trade.exit_date >= week_ago
    ).all()
    
    total_pnl = sum(t.profit_loss for t in trades if t.profit_loss)
    total_trades = len(trades)
    wins = len([t for t in trades if t.profit_loss and t.profit_loss > 0])
    
    return {
        'pnl': total_pnl,
        'trades': total_trades,
        'wins': wins,
        'win_rate': (wins / total_trades * 100) if total_trades > 0 else 0
    }

def get_performance_by_day():
    """Get performance by day of week"""
    from calendar import day_name
    
    trades = Trade.query.filter_by(
        user_id=current_user.id,
        status='CLOSED'
    ).all()
    
    day_stats = {i: {'wins': 0, 'losses': 0, 'pnl': 0} for i in range(7)}
    
    for trade in trades:
        if trade.exit_date and trade.profit_loss:
            day = trade.exit_date.weekday()
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
    today = datetime.utcnow().date()
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
        Trade.entry_date >= datetime.utcnow() - timedelta(days=days)
    ).count()
    
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