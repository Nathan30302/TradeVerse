"""
Admin Routes — lightweight token URL for platform metrics.

Legacy URL (supported): GET /admin/stats?admin_token=<secret>

Configure on Render:
  ADMIN_TOKEN=mysecret123

If ADMIN_TOKEN is unset, ADMIN_TOKEN falls back to OWNER_ADMIN_TOKEN so one secret can cover
both /owner/unlock and /admin/stats.

Tokens are compared in constant time; unequal lengths never call compare_digest (avoids 500).
"""

from __future__ import annotations

import secrets as secrets_stdlib
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, abort, current_app, render_template, request
from sqlalchemy.orm import joinedload

from app.models.user import User
from app.models.trade import Trade

bp = Blueprint('admin', __name__, url_prefix='/admin')


def _expected_admin_query_token() -> str:
    """Secret that must match request.args['admin_token']."""
    raw = (current_app.config.get('ADMIN_TOKEN') or '').strip()
    if raw:
        return raw
    raw = (current_app.config.get('OWNER_ADMIN_TOKEN') or '').strip()
    if raw:
        return raw
    return ''


def require_admin_token(f):
    """
    Require ?admin_token= matching ADMIN_TOKEN (or OWNER_ADMIN_TOKEN if ADMIN_TOKEN unset).
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        expected = _expected_admin_query_token()
        if not expected:
            current_app.logger.warning(
                "GET /admin/stats blocked: set ADMIN_TOKEN or OWNER_ADMIN_TOKEN in the environment."
            )
            abort(503)

        submitted = (request.args.get('admin_token') or '').strip()
        if len(submitted) != len(expected):
            abort(401)
        if not secrets_stdlib.compare_digest(submitted, expected):
            abort(401)

        return f(*args, **kwargs)

    return decorated_function


@bp.route('/stats')
@require_admin_token
def stats():
    """Admin stats page — platform-wide usage (token-gated, no login required)."""

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    total_users = User.query.count()

    users_today = User.query.filter(
        User.created_at >= today_start,
        User.created_at < today_end,
    ).count()

    total_trades = Trade.query.filter(Trade.status == 'CLOSED').count()

    trades_today = Trade.query.filter(
        Trade.entry_date >= today_start,
        Trade.entry_date < today_end,
    ).count()

    latest_users = User.query.order_by(User.created_at.desc()).limit(5).all()

    latest_trades = (
        Trade.query.options(joinedload(Trade.trader))
        .order_by(Trade.created_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        'admin/stats.html',
        app_name=current_app.config.get('APP_NAME', 'TradeVerse'),
        generated_at=datetime.utcnow(),
        total_users=total_users,
        users_today=users_today,
        total_trades=total_trades,
        trades_today=trades_today,
        latest_users=latest_users,
        latest_trades=latest_trades,
    )
