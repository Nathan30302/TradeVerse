"""
Admin Routes
Owner-only stats and administration page
"""

from flask import Blueprint, render_template, request, abort
from flask_login import login_required, current_user
from app import db
from app.models.user import User
from app.models.trade import Trade
from datetime import datetime, timedelta
import os

bp = Blueprint('admin', __name__, url_prefix='/admin')

def is_admin():
    """Check if the current user is the owner via admin token"""
    admin_token = os.environ.get('ADMIN_TOKEN')
    # If no admin token configured, deny access
    if not admin_token:
        return False
    # Check if user has admin_token in session (set after验证)
    return request.session.get('is_admin', False)

def require_admin_token(f):
    """Decorator to require valid admin token"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_token = os.environ.get('ADMIN_TOKEN')
        # Get token from query param or header
        token = request.args.get('admin_token') or request.headers.get('X-Admin-Token')
        if token != admin_token:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/stats')
@require_admin_token
def stats():
    """Admin stats page - shows platform-wide usage data"""
    
    # Get today's date range
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    
    # Total users
    total_users = User.query.count()
    
    # Users created today
    users_today = User.query.filter(
        User.created_at >= today_start,
        User.created_at < today_end
    ).count()
    
    # Total trades (all closed trades)
    total_trades = Trade.query.filter(Trade.status == 'CLOSED').count()
    
    # Trades created today (based on entry_date)
    trades_today = Trade.query.filter(
        Trade.entry_date >= today_start,
        Trade.entry_date < today_end
    ).count()
    
    # Latest 5 users
    latest_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    
    # Latest 5 trades
    latest_trades = Trade.query.order_by(Trade.created_at.desc()).limit(5).all()
    
    return render_template('admin/stats.html',
                          total_users=total_users,
                          users_today=users_today,
                          total_trades=total_trades,
                          trades_today=trades_today,
                          latest_users=latest_users,
                          latest_trades=latest_trades)

