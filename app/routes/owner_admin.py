"""
Owner admin dashboard (RBAC secured).

Owner has full access and is excluded from billing enforcement.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, redirect, render_template, url_for
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models.user import User
from app.models.trade import Trade
from app.services.entitlements import is_owner_user

bp = Blueprint("owner_admin", __name__, url_prefix="/owner")


@bp.route("/")
@login_required
def index():
    """Shortcut to analytics."""
    _require_owner()
    return redirect(url_for("owner_admin.platform_stats"))


def _require_owner():
    if not current_user.is_authenticated:
        abort(401)
    if (getattr(current_user, "role", "user") or "user").lower() != "owner" and not is_owner_user(current_user):
        abort(404)


def _safe_scalar(q):
    try:
        return int(q.scalar() or 0)
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return 0


@bp.route("/stats")
@login_required
def platform_stats():
    """
    Standalone owner analytics: usage + trade mix (minimal journal chrome).
    """
    _require_owner()

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    days_30_ago = now - timedelta(days=30)

    total_users = _safe_scalar(db.session.query(func.count(User.id)))
    users_new_30d = _safe_scalar(
        db.session.query(func.count(User.id)).filter(User.created_at >= days_30_ago)
    )
    users_before_30d = max(0, total_users - users_new_30d)

    total_trades = _safe_scalar(db.session.query(func.count(Trade.id)))
    open_trades = _safe_scalar(
        db.session.query(func.count(Trade.id)).filter(Trade.status == "OPEN")
    )
    closed_trades = _safe_scalar(
        db.session.query(func.count(Trade.id)).filter(Trade.status == "CLOSED")
    )

    trades_7d = _safe_scalar(
        db.session.query(func.count(Trade.id)).filter(Trade.created_at >= week_ago)
    )

    active_users_7d = _safe_scalar(
        db.session.query(func.count(func.distinct(Trade.user_id))).filter(
            Trade.created_at >= week_ago
        )
    )

    by_trade_type = []
    by_trade_status = []
    top_symbols = []
    top_strategies = []
    try:
        by_trade_type = (
            db.session.query(Trade.trade_type, func.count(Trade.id))
            .group_by(Trade.trade_type)
            .order_by(func.count(Trade.id).desc())
            .all()
        )
        by_trade_status = (
            db.session.query(Trade.status, func.count(Trade.id))
            .group_by(Trade.status)
            .order_by(func.count(Trade.id).desc())
            .all()
        )
        top_symbols = (
            db.session.query(Trade.symbol, func.count(Trade.id))
            .group_by(Trade.symbol)
            .order_by(func.count(Trade.id).desc())
            .limit(20)
            .all()
        )
        top_strategies = (
            db.session.query(Trade.strategy, func.count(Trade.id))
            .filter(Trade.strategy.isnot(None), Trade.strategy != "")
            .group_by(Trade.strategy)
            .order_by(func.count(Trade.id).desc())
            .limit(20)
            .all()
        )
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

    by_tier = []
    by_status = []
    try:
        by_tier = (
            db.session.query(User.subscription_tier, func.count(User.id))
            .group_by(User.subscription_tier)
            .all()
        )
        by_status = (
            db.session.query(User.subscription_status, func.count(User.id))
            .group_by(User.subscription_status)
            .all()
        )
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

    return render_template(
        "owner_admin/platform_stats.html",
        total_users=total_users,
        users_new_30d=users_new_30d,
        users_before_30d=users_before_30d,
        total_trades=total_trades,
        open_trades=open_trades,
        closed_trades=closed_trades,
        trades_7d=trades_7d,
        active_users_7d=active_users_7d,
        by_trade_type=by_trade_type,
        by_trade_status=by_trade_status,
        by_tier=by_tier,
        by_status=by_status,
        top_symbols=top_symbols,
        top_strategies=top_strategies,
    )


@bp.route("/dashboard")
@login_required
def dashboard():
    """Back-compat: full journal shell; prefer /owner/stats for analytics-only view."""
    _require_owner()
    return redirect(url_for("owner_admin.platform_stats"))
