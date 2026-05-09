"""
Admin Routes — lightweight token URL for platform metrics.

Legacy URL (supported): GET /admin/stats?admin_token=<secret>

Configure on Render:
  ADMIN_TOKEN=mysecret123

If ADMIN_TOKEN is unset, ADMIN_TOKEN falls back to OWNER_ADMIN_TOKEN so one secret can cover
both /owner/unlock and /admin/stats.

Queries use SQLAlchemy Core on User.__table__ / Trade.__table__ only so this page keeps working
when the ORM model has columns that are not migrated yet (avoids 500 on schema drift).
"""

from __future__ import annotations

import secrets as secrets_stdlib
from datetime import datetime, timedelta, timezone
from functools import wraps
from types import SimpleNamespace

from flask import Blueprint, abort, current_app, render_template, request
from sqlalchemy import and_, func, select

from app import db
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


def _scalar_int(q) -> int:
    try:
        v = db.session.scalar(q)
        return int(v or 0)
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return 0


@bp.route('/stats')
@require_admin_token
def stats():
    """Admin stats page — platform-wide usage (token-gated, no login required)."""

    # UTC-aware window so Postgres timestamptz compares cleanly (avoids 500 on Render).
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    ut = User.__table__
    tt = Trade.__table__

    total_users = _scalar_int(select(func.count()).select_from(ut))

    users_today = _scalar_int(
        select(func.count())
        .select_from(ut)
        .where(and_(ut.c.created_at >= today_start, ut.c.created_at < today_end))
    )

    total_trades = _scalar_int(
        select(func.count()).select_from(tt).where(tt.c.status == 'CLOSED')
    )

    trades_today = _scalar_int(
        select(func.count())
        .select_from(tt)
        .where(and_(tt.c.entry_date >= today_start, tt.c.entry_date < today_end))
    )

    urows = db.session.execute(
        select(ut.c.id, ut.c.username, ut.c.email, ut.c.created_at)
        .order_by(ut.c.created_at.desc())
        .limit(5)
    ).all()

    latest_users = [
        SimpleNamespace(
            id=r.id,
            username=r.username or '',
            email=r.email or '',
            created_at=r.created_at,
        )
        for r in urows
    ]

    # LEFT JOIN so orphaned trade rows still show if user row missing
    j = tt.outerjoin(ut, tt.c.user_id == ut.c.id)
    trows = db.session.execute(
        select(
            tt.c.symbol,
            tt.c.trade_type,
            tt.c.profit_loss,
            tt.c.created_at,
            ut.c.username,
        )
        .select_from(j)
        .order_by(tt.c.created_at.desc())
        .limit(5)
    ).all()

    latest_trades = []
    for r in trows:
        uname = r.username
        trader = SimpleNamespace(username=uname) if uname else None
        latest_trades.append(
            SimpleNamespace(
                symbol=r.symbol or '',
                trade_type=r.trade_type or 'BUY',
                profit_loss=r.profit_loss,
                created_at=r.created_at,
                trader=trader,
            )
        )

    return render_template(
        'admin/stats.html',
        app_name=current_app.config.get('APP_NAME', 'TradeVerse'),
        generated_at=datetime.now(timezone.utc),
        total_users=total_users,
        users_today=users_today,
        total_trades=total_trades,
        trades_today=trades_today,
        latest_users=latest_users,
        latest_trades=latest_trades,
    )
