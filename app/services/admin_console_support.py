"""
Helpers for token-gated admin console: timed links, audit logging, metrics, health.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from app.utils.timeutil import utc_now
from typing import Any

from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import and_, exists, func, select, text

from app.services.owner_email import mail_is_configured

TIMED_SALT = "tv-admin-ts-v1"


def timed_serializer(app):
    return URLSafeTimedSerializer(app.secret_key, salt=TIMED_SALT)


def generate_admin_ts_token(app) -> str:
    """Issue a short-lived token for ?admin_ts= (same session grant as admin_token)."""
    return timed_serializer(app).dumps({"v": 1})


def verify_admin_ts_token(app, token: str | None) -> bool:
    if not token or not str(token).strip():
        return False
    max_age = int(app.config.get("ADMIN_TIMED_LINK_MAX_AGE", 3600))
    try:
        timed_serializer(app).loads(str(token).strip(), max_age=max_age)
        return True
    except Exception:
        return False


def log_admin_event(db, event_type: str, meta: dict | None = None, ip: str | None = None) -> None:
    from app.models.admin_console import AdminConsoleEvent

    try:
        row = AdminConsoleEvent(
            event_type=event_type[:40],
            meta_json=json.dumps(meta, default=str)[:65000] if meta else None,
            ip_address=(ip or "")[:45] or None,
            created_at=utc_now(),
        )
        db.session.add(row)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


def count_admin_emails_today(db) -> int:
    """Rough SMTP sends initiated from admin email UI today (UTC date boundary)."""
    from app.models.admin_console import AdminConsoleEvent

    start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    et = AdminConsoleEvent.__table__
    try:
        return int(
            db.session.scalar(
                select(func.count())
                .select_from(et)
                .where(
                    et.c.event_type.in_(["email_test", "email_bulk"]),
                    et.c.created_at >= start,
                )
            )
            or 0
        )
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return 0


def _safe_scalar(db, q) -> int | None:
    try:
        return int(db.session.scalar(q) or 0)
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


def _table_exists(db, name: str) -> bool:
    from sqlalchemy import inspect as sqla_inspect

    try:
        return bool(sqla_inspect(db.engine).has_table(name))
    except Exception:
        return False


def _safe_count_table(db, table: str) -> int | None:
    allowed = {
        "imported_trade_sources",
        "trade_replay_events",
        "playbook_setups",
        "users",
        "trades",
    }
    if table not in allowed:
        return None
    if not _table_exists(db, table):
        return None
    try:
        return int(db.session.scalar(text(f"SELECT COUNT(*) FROM {table}")) or 0)
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


def get_alembic_revision(db) -> str | None:
    if not _table_exists(db, "alembic_version"):
        return None
    try:
        return db.session.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


def admin_health_snapshot(app, db) -> dict[str, Any]:
    db_ok = True
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
        try:
            db.session.rollback()
        except Exception:
            pass

    return {
        "database_ok": db_ok,
        "alembic_revision": get_alembic_revision(db),
        "mail_configured": mail_is_configured(app.config),
        "sentry_configured": bool(os.environ.get("SENTRY_DSN")),
        "worker_heartbeat": (os.environ.get("WORKER_LAST_HEARTBEAT") or "").strip() or None,
        "maintenance_mode": bool(app.config.get("MAINTENANCE_MODE")),
    }


def gather_admin_dashboard_metrics(db, User, Trade) -> dict[str, Any]:
    """
    Extra tiles for admin overview: cohorts, feature usage, quality checks.
    Uses Core where possible; missing tables/columns degrade gracefully.
    """
    from sqlalchemy import inspect as sqla_inspect

    now = datetime.now(timezone.utc)
    ut = User.__table__
    tt = Trade.__table__

    out: dict[str, Any] = {
        "schema_notes": [],
        "signup_wow": None,
        "activation_rate_30d": None,
        "inactive_buckets": {},
        "imports_total": _safe_count_table(db, "imported_trade_sources"),
        "replay_events_total": _safe_count_table(db, "trade_replay_events"),
        "playbook_setups_total": _safe_count_table(db, "playbook_setups"),
        "utm_top": [],
        "orphan_trades": None,
        "negative_lots": None,
    }

    # --- Rolling 7d signup comparison (UTC) ---
    try:
        w0 = now - timedelta(days=7)
        w1 = now - timedelta(days=14)
        cur_week = _safe_scalar(db, select(func.count()).select_from(ut).where(ut.c.created_at >= w0))
        prev_week = _safe_scalar(
            db,
            select(func.count())
            .select_from(ut)
            .where(and_(ut.c.created_at >= w1, ut.c.created_at < w0)),
        )
        if cur_week is not None and prev_week is not None:
            out["signup_wow"] = {"current_7d": cur_week, "previous_7d": prev_week}
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

    # --- Activation: users in last 30d with >=1 closed trade ---
    try:
        cut = now - timedelta(days=30)
        closed_exists = exists(
            select(1)
            .select_from(tt)
            .where(and_(tt.c.user_id == ut.c.id, tt.c.status == "CLOSED"))
        )
        num_act = _safe_scalar(
            db,
            select(func.count()).select_from(ut).where(and_(ut.c.created_at >= cut, closed_exists)),
        )
        den = _safe_scalar(db, select(func.count()).select_from(ut).where(ut.c.created_at >= cut))
        if num_act is not None and den is not None and den > 0:
            out["activation_rate_30d"] = round(100.0 * num_act / den, 1)
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

    # --- Inactive buckets (no login/update proxy: coalesce last_login, created_at) ---
    try:
        activity = func.coalesce(ut.c.last_login, ut.c.created_at)
        for label, days in (("7d", 7), ("14d", 14), ("30d", 30)):
            cutoff = utc_now() - timedelta(days=days)
            n = _safe_scalar(
                db,
                select(func.count())
                .select_from(ut)
                .where(
                    ut.c.is_active.is_(True),
                    activity.isnot(None),
                    activity < cutoff,
                ),
            )
            if n is not None:
                out["inactive_buckets"][label] = n
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

    # --- UTM / referral (column may be missing pre-migration) ---
    try:
        insp = sqla_inspect(db.engine)
        if not insp.has_table("users"):
            raise RuntimeError("no users table")
        ucols = {c["name"] for c in insp.get_columns("users")}
        if "signup_utm_source" in ucols:
            rows = db.session.execute(
                select(ut.c.signup_utm_source, func.count())
                .where(ut.c.signup_utm_source.isnot(None), ut.c.signup_utm_source != "")
                .group_by(ut.c.signup_utm_source)
                .order_by(func.count().desc())
                .limit(8)
            ).all()
            out["utm_top"] = [(r[0], int(r[1] or 0)) for r in rows]
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

    # --- Data quality ---
    try:
        j = tt.outerjoin(ut, tt.c.user_id == ut.c.id)
        out["orphan_trades"] = _safe_scalar(
            db, select(func.count()).select_from(j).where(ut.c.id.is_(None))
        )
    except Exception:
        out["schema_notes"].append("Orphan trade count unavailable (query failed).")
        try:
            db.session.rollback()
        except Exception:
            pass

    try:
        out["negative_lots"] = _safe_scalar(
            db, select(func.count()).select_from(tt).where(tt.c.lot_size < 0)
        )
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

    return out
