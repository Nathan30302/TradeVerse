"""
Admin Routes — token URL + signed session for platform metrics and email outreach.

Bookmark URL (first visit): GET /admin/stats?admin_token=<secret>

Configure on Render:
  ADMIN_TOKEN=mysecret123

If ADMIN_TOKEN is unset, ADMIN_TOKEN falls back to OWNER_ADMIN_TOKEN so one secret can cover
both /owner/unlock and /admin/*.

After a successful token match, a Flask session flag grants access to /admin/stats and
/admin/email without repeating the query parameter (URL is redirected to strip ?admin_token=).

Queries on the stats page use SQLAlchemy Core on User.__table__ / Trade.__table__ only so this
page keeps working when the ORM model has columns that are not migrated yet (avoids 500 on schema drift).
"""

from __future__ import annotations

import secrets as secrets_stdlib
from datetime import datetime, timedelta, timezone
from functools import wraps
from types import SimpleNamespace

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_mail import Message
from sqlalchemy import and_, func, select

from app import db, mail
from app.models.user import User
from app.models.trade import Trade
from app.services.owner_email import (
    apply_email_placeholders,
    audience_users,
    mail_is_configured,
    mail_sender_address,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")

SESSION_ADMIN_LINK = "tv_admin_link"


def _expected_admin_query_token() -> str:
    """Secret that must match request.args['admin_token']."""
    raw = (current_app.config.get("ADMIN_TOKEN") or "").strip()
    if raw:
        return raw
    raw = (current_app.config.get("OWNER_ADMIN_TOKEN") or "").strip()
    if raw:
        return raw
    return ""


def require_admin_link(f):
    """
    Require valid ?admin_token= once per browser session, then rely on signed session.

    If ADMIN_TOKEN / OWNER_ADMIN_TOKEN is unset, respond with 503.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        expected = _expected_admin_query_token()
        if not expected:
            current_app.logger.warning(
                "Admin route blocked: set ADMIN_TOKEN or OWNER_ADMIN_TOKEN in the environment."
            )
            abort(503)

        if session.get(SESSION_ADMIN_LINK):
            return f(*args, **kwargs)

        submitted = (request.args.get("admin_token") or "").strip()
        if len(submitted) != len(expected):
            abort(401)
        if not secrets_stdlib.compare_digest(submitted, expected):
            abort(401)

        session[SESSION_ADMIN_LINK] = True
        session.modified = True
        if request.args.get("admin_token"):
            return redirect(url_for(request.endpoint, **(request.view_args or {})))
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


def _safe_scalar(q):
    try:
        return int(q.scalar() or 0)
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return 0


@bp.route("/lock")
def admin_lock():
    """Clear admin-link session (revokes bookmark access until token is supplied again)."""
    session.pop(SESSION_ADMIN_LINK, None)
    flash("Admin link session cleared.", "info")
    return redirect(url_for("main.index"))


@bp.route("/stats")
@require_admin_link
def stats():
    """Admin stats page — platform-wide usage (token-gated, no login required)."""

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
        select(func.count()).select_from(tt).where(tt.c.status == "CLOSED")
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
            username=r.username or "",
            email=r.email or "",
            created_at=r.created_at,
        )
        for r in urows
    ]

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
                symbol=r.symbol or "",
                trade_type=r.trade_type or "BUY",
                profit_loss=r.profit_loss,
                created_at=r.created_at,
                trader=trader,
            )
        )

    return render_template(
        "admin/stats.html",
        app_name=current_app.config.get("APP_NAME", "TradeVerse"),
        generated_at=datetime.now(timezone.utc),
        total_users=total_users,
        users_today=users_today,
        total_trades=total_trades,
        trades_today=trades_today,
        latest_users=latest_users,
        latest_trades=latest_trades,
    )


@bp.route("/email", methods=["GET", "POST"])
@require_admin_link
def email_outreach():
    """
    Send plain-text emails (same capabilities as owner console) via admin token session.
    Test sends use the email address you enter (no login required).
    """
    cfg = current_app.config
    mail_ok = mail_is_configured(cfg)
    app_name = cfg.get("APP_NAME", "TradeVerse")
    login_url = url_for("auth.login", _external=True)
    inactive_default = 14
    max_per_run = int(cfg.get("OWNER_EMAIL_MAX_PER_RUN", 200))

    if request.method == "POST":
        if not mail_ok:
            flash(
                "Mail is not configured. Set MAIL_USERNAME, MAIL_PASSWORD, and MAIL_DEFAULT_SENDER "
                "(or rely on MAIL_USERNAME as sender) on the server.",
                "danger",
            )
            return redirect(url_for("admin.email_outreach"))

        subject_line = (request.form.get("subject") or "").strip()
        body_tpl = (request.form.get("body") or "").strip()
        audience = (request.form.get("audience") or "test_self").strip()
        inactive_days = int(request.form.get("inactive_days") or inactive_default)
        confirm_bulk = request.form.get("confirm_bulk") == "1"

        if not subject_line or not body_tpl:
            flash("Subject and message body are required.", "warning")
            return redirect(url_for("admin.email_outreach"))

        sender = mail_sender_address(cfg)
        if not sender:
            flash("Could not resolve a sender address from mail configuration.", "danger")
            return redirect(url_for("admin.email_outreach"))

        if audience == "test_self":
            test_email = (request.form.get("test_email") or "").strip()
            if not test_email:
                flash("Enter an email address for the test send.", "warning")
                return redirect(url_for("admin.email_outreach"))

            user_row = User.query.filter(
                User.email.isnot(None),
                func.lower(User.email) == func.lower(test_email),
            ).first()
            placeholder_user = user_row or SimpleNamespace(
                username="trader",
                email=test_email,
            )
            body = apply_email_placeholders(
                body_tpl,
                user=placeholder_user,
                app_name=app_name,
                login_url=login_url,
            )
            msg = Message(
                subject=subject_line,
                sender=sender,
                recipients=[test_email],
                body=body,
            )
            try:
                mail.send(msg)
                flash(f"Test email sent to {test_email}.", "success")
            except Exception as exc:
                current_app.logger.exception("Admin-link test email failed")
                flash(f"Send failed: {exc}", "danger")
            return redirect(url_for("admin.email_outreach"))

        if audience in ("all_registered", "inactive"):
            if not confirm_bulk:
                flash(
                    "Confirm the acknowledgement checkbox before sending to many recipients.",
                    "warning",
                )
                return redirect(url_for("admin.email_outreach"))

            candidates = audience_users(
                audience="all_registered" if audience == "all_registered" else "inactive",
                inactive_days=inactive_days,
            )
            truncated = False
            if len(candidates) > max_per_run:
                candidates = candidates[:max_per_run]
                truncated = True

            sent = 0
            failed = 0
            for u in candidates:
                try:
                    body = apply_email_placeholders(
                        body_tpl,
                        user=u,
                        app_name=app_name,
                        login_url=login_url,
                    )
                    msg = Message(
                        subject=subject_line,
                        sender=sender,
                        recipients=[u.email],
                        body=body,
                    )
                    mail.send(msg)
                    sent += 1
                except Exception:
                    current_app.logger.warning(
                        "Admin bulk email failed for user id=%s", u.id, exc_info=True
                    )
                    failed += 1

            parts = [f"Finished: {sent} sent", f"{failed} failed."]
            if truncated:
                parts.append(
                    f"Capped at {max_per_run} recipients per run (set OWNER_EMAIL_MAX_PER_RUN to raise)."
                )
            flash(" ".join(parts), "success" if failed == 0 else "warning")
            return redirect(url_for("admin.email_outreach"))

        flash("Unknown audience selection.", "danger")
        return redirect(url_for("admin.email_outreach"))

    activity = func.coalesce(User.last_login, User.created_at)
    cutoff = datetime.utcnow() - timedelta(days=inactive_default)
    n_all = _safe_scalar(
        db.session.query(func.count(User.id)).filter(
            User.is_active.is_(True),
            User.email.isnot(None),
            User.email != "",
        )
    )
    n_inactive = _safe_scalar(
        db.session.query(func.count(User.id)).filter(
            User.is_active.is_(True),
            User.email.isnot(None),
            User.email != "",
            activity.isnot(None),
            activity < cutoff,
        )
    )

    return render_template(
        "admin/email_outreach.html",
        mail_configured=mail_ok,
        app_name=app_name,
        login_url=login_url,
        recipient_count_all=n_all,
        recipient_count_inactive=n_inactive,
        inactive_days_default=inactive_default,
        max_per_run=max_per_run,
    )
