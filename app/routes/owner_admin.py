"""
Owner admin dashboard (RBAC secured).

Owner has full access and is excluded from billing enforcement.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, render_template
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models.user import User
from app.models.trade import Trade
from app.services.entitlements import is_owner_user

bp = Blueprint("owner_admin", __name__, url_prefix="/owner")


def _require_owner():
    if not current_user.is_authenticated:
        abort(401)
    if (getattr(current_user, "role", "user") or "user").lower() != "owner" and not is_owner_user(current_user):
        abort(404)


@bp.route("/dashboard")
@login_required
def dashboard():
    _require_owner()

    total_users = User.query.count()
    # Avoid Query.count() on ORM entities; it may SELECT missing columns if
    # migrations (e.g. playbook_setup_id) haven't been applied yet.
    total_trades = int(db.session.query(func.count(Trade.id)).scalar() or 0)
    closed_trades = int(
        db.session.query(func.count(Trade.id))
        .filter(Trade.status == "CLOSED")
        .scalar()
        or 0
    )

    by_tier = (
        []
    )
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
        # tolerate schema drift
        by_tier = []
        by_status = []

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    active_users_7d = (
        db.session.query(Trade.user_id)
        .filter(Trade.created_at >= week_ago)
        .distinct()
        .count()
    )

    return render_template(
        "owner_admin/dashboard.html",
        total_users=total_users,
        total_trades=total_trades,
        closed_trades=closed_trades,
        by_tier=by_tier,
        by_status=by_status,
        active_users_7d=active_users_7d,
    )

