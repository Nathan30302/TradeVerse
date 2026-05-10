"""
Owner admin dashboard (RBAC + optional platform unlock).

Primary access: User.role == "owner", or email/username allowlists (OWNER_EMAILS / OWNER_USERNAMES).

Hosted deployments (e.g. Render) often only set SECRET_KEY. Logged-in founders can unlock a browser
session at /owner/unlock using OWNER_ADMIN_TOKEN if set, otherwise the same value as SECRET_KEY.
"""

from __future__ import annotations

import secrets as secrets_stdlib
from datetime import datetime, timedelta

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
from flask_login import login_required, current_user
from flask_mail import Message
from sqlalchemy import func

from app import db, mail
from app.models.user import User
from app.models.trade import Trade
from app.services.entitlements import _safe_getattr, is_owner_user
from app.services.owner_email import (
    apply_email_placeholders,
    audience_users,
    mail_is_configured,
    mail_sender_address,
)

bp = Blueprint("owner_admin", __name__, url_prefix="/owner")

SESSION_OWNER_PLATFORM = "tv_owner_platform"


def _safe_internal_path(candidate: str | None) -> str | None:
    """Avoid open redirects: only allow same-origin relative paths."""
    c = (candidate or "").strip()
    if c.startswith("/") and not c.startswith("//"):
        return c
    return None


def _rbac_owner_ok() -> bool:
    role = (_safe_getattr(current_user, "role", None) or "user").strip().lower()
    return role == "owner" or is_owner_user(current_user)


def _platform_session_ok() -> bool:
    return bool(session.get(SESSION_OWNER_PLATFORM))


def owner_platform_access_granted() -> bool:
    """Whether current login may open /owner/* (RBAC or unlocked session)."""
    if not getattr(current_user, "is_authenticated", False):
        return False
    return _rbac_owner_ok() or _platform_session_ok()


def owner_platform_session_only() -> bool:
    """Session passphrase unlock without DB owner role / allowlist."""
    if not getattr(current_user, "is_authenticated", False):
        return False
    return _platform_session_ok() and not _rbac_owner_ok()


def _expected_unlock_secret() -> str:
    """
    Token that must be POSTed to /owner/unlock.

    OWNER_ADMIN_TOKEN wins when set (recommended for production).
    Otherwise falls back to SECRET_KEY so a single Render secret can unlock analytics.
    """
    raw = current_app.config.get("OWNER_ADMIN_TOKEN")
    if raw is not None and str(raw).strip() != "":
        return str(raw).strip()
    sk = current_app.config.get("SECRET_KEY") or ""
    return str(sk).strip()


def _owner_gate():
    """
    Returns None if access allowed, else a redirect to unlock with flash.
    """
    if not current_user.is_authenticated:
        abort(401)
    if owner_platform_access_granted():
        return None
    flash(
        "Platform analytics requires owner access or a one-time unlock. "
        "Use /owner/unlock with your deployment secret (same as SECRET_KEY on Render unless you set OWNER_ADMIN_TOKEN).",
        "warning",
    )
    return redirect(url_for("owner_admin.unlock", next=request.full_path))


def _safe_scalar(q):
    try:
        return int(q.scalar() or 0)
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return 0


def _active_traders_7d(week_ago_naive: datetime) -> int:
    """Count distinct users with a trade in the lookback window (Postgres/SQLite safe)."""
    try:
        return int(
            db.session.query(func.count(func.distinct(Trade.user_id)))
            .filter(Trade.created_at >= week_ago_naive)
            .scalar()
            or 0
        )
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
    try:
        return (
            db.session.query(Trade.user_id)
            .filter(Trade.created_at >= week_ago_naive)
            .distinct()
            .count()
        )
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return 0


@bp.route("/unlock", methods=["GET", "POST"])
@login_required
def unlock():
    """
    Unlock owner analytics for this browser session using the platform secret.
    """
    expected = _expected_unlock_secret()
    fallback = url_for("owner_admin.platform_stats")
    next_url = _safe_internal_path(request.args.get("next")) or _safe_internal_path(
        request.form.get("next")
    ) or fallback

    if not expected:
        return render_template(
            "owner_admin/unlock.html",
            unlock_disabled=True,
            next_url=next_url,
        )

    if request.method == "POST":
        submitted = (request.form.get("platform_token") or "").strip()
        if not submitted:
            flash("Paste your platform token.", "danger")
        elif not secrets_stdlib.compare_digest(submitted, expected):
            flash("Token did not match. Check OWNER_ADMIN_TOKEN or SECRET_KEY on the server.", "danger")
        else:
            session[SESSION_OWNER_PLATFORM] = True
            session.permanent = True
            flash("Platform analytics unlocked for this browser session.", "success")
            return redirect(next_url)

    uses_fallback = not (current_app.config.get("OWNER_ADMIN_TOKEN") or "").strip()
    return render_template(
        "owner_admin/unlock.html",
        unlock_disabled=False,
        next_url=next_url,
        uses_secret_key_fallback=uses_fallback,
    )


@bp.route("/lock", methods=["POST"])
@login_required
def lock_platform():
    """Clear passphrase-based unlock (RBAC owners unaffected)."""
    session.pop(SESSION_OWNER_PLATFORM, None)
    flash("Platform unlock cleared for this browser.", "info")
    return redirect(url_for("dashboard.index"))


@bp.route("/stats")
@login_required
def platform_stats():
    """
    Standalone owner analytics: usage + trade mix (minimal journal chrome).
    """
    gate = _owner_gate()
    if gate:
        return gate

    # Naive UTC matches typical TIMESTAMP columns and avoids aware/naive compare issues on Postgres.
    week_ago_naive = datetime.utcnow() - timedelta(days=7)
    days_30_naive = datetime.utcnow() - timedelta(days=30)

    total_users = _safe_scalar(db.session.query(func.count(User.id)))
    users_new_30d = _safe_scalar(
        db.session.query(func.count(User.id)).filter(User.created_at >= days_30_naive)
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
        db.session.query(func.count(Trade.id)).filter(Trade.created_at >= week_ago_naive)
    )

    active_users_7d = _active_traders_7d(week_ago_naive)

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


@bp.route("/email", methods=["GET", "POST"])
@login_required
def email_outreach():
    """
    Send encouragement / announcement emails to registered users (plain text).
    Requires MAIL_* env configuration; bulk sends are capped per request.
    """
    gate = _owner_gate()
    if gate:
        return gate

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
            return redirect(url_for("owner_admin.email_outreach"))

        subject_line = (request.form.get("subject") or "").strip()
        body_tpl = (request.form.get("body") or "").strip()
        audience = (request.form.get("audience") or "test_self").strip()
        inactive_days = int(request.form.get("inactive_days") or inactive_default)
        confirm_bulk = request.form.get("confirm_bulk") == "1"

        if not subject_line or not body_tpl:
            flash("Subject and message body are required.", "warning")
            return redirect(url_for("owner_admin.email_outreach"))

        sender = mail_sender_address(cfg)
        if not sender:
            flash("Could not resolve a sender address from mail configuration.", "danger")
            return redirect(url_for("owner_admin.email_outreach"))

        if audience == "test_self":
            if not current_user.email:
                flash("Your account has no email address — cannot send a test.", "danger")
                return redirect(url_for("owner_admin.email_outreach"))
            body = apply_email_placeholders(
                body_tpl,
                user=current_user,
                app_name=app_name,
                login_url=login_url,
            )
            msg = Message(
                subject=subject_line,
                sender=sender,
                recipients=[current_user.email],
                body=body,
            )
            try:
                mail.send(msg)
                flash(f"Test email sent to {current_user.email}.", "success")
            except Exception as exc:
                current_app.logger.exception("Owner test email failed")
                flash(f"Send failed: {exc}", "danger")
            return redirect(url_for("owner_admin.email_outreach"))

        if audience in ("all_registered", "inactive"):
            if not confirm_bulk:
                flash(
                    "Confirm the acknowledgement checkbox before sending to many recipients.",
                    "warning",
                )
                return redirect(url_for("owner_admin.email_outreach"))

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
                        "Owner bulk email failed for user id=%s", u.id, exc_info=True
                    )
                    failed += 1

            parts = [f"Finished: {sent} sent", f"{failed} failed."]
            if truncated:
                parts.append(f"Capped at {max_per_run} recipients per run (set OWNER_EMAIL_MAX_PER_RUN to raise).")
            flash(" ".join(parts), "success" if failed == 0 else "warning")
            return redirect(url_for("owner_admin.email_outreach"))

        flash("Unknown audience selection.", "danger")
        return redirect(url_for("owner_admin.email_outreach"))

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
        "owner_admin/email_outreach.html",
        mail_configured=mail_ok,
        app_name=app_name,
        login_url=login_url,
        recipient_count_all=n_all,
        recipient_count_inactive=n_inactive,
        inactive_days_default=inactive_default,
        max_per_run=max_per_run,
    )


@bp.route("/dashboard")
@login_required
def dashboard():
    """Back-compat: prefer /owner/stats for analytics-only view."""
    gate = _owner_gate()
    if gate:
        return gate
    return redirect(url_for("owner_admin.platform_stats"))


@bp.route("/")
@login_required
def index():
    """Shortcut to analytics."""
    gate = _owner_gate()
    if gate:
        return gate
    return redirect(url_for("owner_admin.platform_stats"))
