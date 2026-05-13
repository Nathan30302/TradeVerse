"""
Admin Routes — token URL, timed URL (?admin_ts=), and signed session for ops tooling.

Bookmark: GET /admin/stats?admin_token=<secret> or ?admin_ts=<signed>

Configure: ADMIN_TOKEN or OWNER_ADMIN_TOKEN.
"""

from __future__ import annotations

import csv
import io
import json
import random
import secrets as secrets_stdlib
from datetime import datetime, timedelta, timezone
from app.utils.timeutil import utc_now
from functools import wraps
from types import SimpleNamespace

from flask import (
    Blueprint,
    Response,
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
from app.models.admin_console import AdminEmailDraft
from app.models.user import User
from app.models.trade import Trade
from app.services.admin_console_support import (
    admin_health_snapshot,
    count_admin_emails_today,
    gather_admin_dashboard_metrics,
    generate_admin_ts_token,
    log_admin_event,
    verify_admin_ts_token,
)
from app.services.owner_email import (
    apply_email_placeholders,
    audience_users,
    mail_is_configured,
    mail_sender_address,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")

SESSION_ADMIN_LINK = "tv_admin_link"
SESSION_ADMIN_BULK_CODE = "tv_admin_bulk_code"


def _expected_admin_query_token() -> str:
    raw = (current_app.config.get("ADMIN_TOKEN") or "").strip()
    if raw:
        return raw
    raw = (current_app.config.get("OWNER_ADMIN_TOKEN") or "").strip()
    if raw:
        return raw
    return ""


def _client_ip() -> str | None:
    h = (request.headers.get("X-Forwarded-For") or "").strip()
    if h:
        return h.split(",")[0].strip()[:45] or None
    return (request.remote_addr or "")[:45] or None


def _refresh_bulk_challenge() -> str:
    code = f"{secrets_stdlib.randbelow(900000) + 100000:06d}"
    session[SESSION_ADMIN_BULK_CODE] = code
    session.modified = True
    return code


def _bulk_challenge_code() -> str | None:
    return session.get(SESSION_ADMIN_BULK_CODE)


def require_admin_link(f):
    """Gate with session, ?admin_ts= (timed), or ?admin_token=."""

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

        ts = (request.args.get("admin_ts") or "").strip()
        if ts:
            if verify_admin_ts_token(current_app, ts):
                session[SESSION_ADMIN_LINK] = True
                session.modified = True
                if request.args.get("admin_ts"):
                    return redirect(url_for(request.endpoint, **(request.view_args or {})))
            abort(401)

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
    session.pop(SESSION_ADMIN_LINK, None)
    session.pop(SESSION_ADMIN_BULK_CODE, None)
    flash("Admin link session cleared.", "info")
    return redirect(url_for("main.index"))


@bp.route("/issue-link", methods=["GET"])
@require_admin_link
def issue_timed_link():
    """Return a fresh short-lived admin URL (same session grant). Requires admin session."""
    try:
        tok = generate_admin_ts_token(current_app)
        base = request.host_url.rstrip("/")
        path = url_for("admin.stats")
        url = f"{base}{path}?admin_ts={tok}"
        return Response(
            json.dumps({"ok": True, "url": url, "max_age": current_app.config.get("ADMIN_TIMED_LINK_MAX_AGE", 3600)}),
            mimetype="application/json",
        )
    except Exception as exc:
        return Response(json.dumps({"ok": False, "error": str(exc)}), mimetype="application/json", status=500)


@bp.route("/stats")
@require_admin_link
def stats():
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

    extended = gather_admin_dashboard_metrics(db, User, Trade)
    health = admin_health_snapshot(current_app, db)

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
        extended=extended,
        health=health,
        emails_sent_today=count_admin_emails_today(db),
        owner_email_cap=int(current_app.config.get("OWNER_EMAIL_MAX_PER_RUN", 200)),
    )


@bp.route("/ops")
@require_admin_link
def ops_console():
    health = admin_health_snapshot(current_app, db)
    log_lines = []
    try:
        from app.models.admin_console import AdminConsoleEvent

        rows = (
            AdminConsoleEvent.query.order_by(AdminConsoleEvent.created_at.desc()).limit(40).all()
        )
        for r in rows:
            log_lines.append(
                {
                    "type": r.event_type,
                    "at": r.created_at,
                    "meta": r.meta_json,
                    "ip": r.ip_address,
                }
            )
    except Exception:
        log_lines = []

    return render_template(
        "admin/ops.html",
        health=health,
        audit_tail=log_lines,
        render_logs_url="https://dashboard.render.com/",
    )


@bp.route("/ops/note", methods=["POST"])
@require_admin_link
def ops_incident_note():
    incident = (request.form.get("incident_ref") or "").strip()[:500]
    if incident:
        log_admin_event(
            db,
            "ops_incident_note",
            {"ref": incident},
            ip=_client_ip(),
        )
        flash("Incident reference recorded in audit log.", "success")
    else:
        flash("Enter a reference or ID.", "warning")
    return redirect(url_for("admin.ops_console"))


@bp.route("/users")
@require_admin_link
def user_search():
    q = (request.args.get("q") or "").strip()
    results = []
    if q:
        like = f"%{q}%"
        if q.isdigit():
            uid = int(q)
            rows = User.query.filter(User.id == uid).limit(20).all()
        else:
            rows = (
                User.query.filter(
                    (User.email.ilike(like)) | (User.username.ilike(like))
                )
                .limit(25)
                .all()
            )
        results = rows
    return render_template("admin/users.html", q=q, results=results)


@bp.route("/users/<int:user_id>")
@require_admin_link
def user_inspect(user_id: int):
    u = User.query.get_or_404(user_id)
    closed_n = _safe_scalar(
        db.session.query(func.count(Trade.id)).filter(
            Trade.user_id == u.id, Trade.status == "CLOSED"
        )
    )
    total_n = _safe_scalar(
        db.session.query(func.count(Trade.id)).filter(Trade.user_id == u.id)
    )
    exports_blocked = False
    try:
        exports_blocked = bool(getattr(u, "exports_blocked", False))
    except Exception:
        pass
    return render_template(
        "admin/user_inspect.html",
        user=u,
        closed_trades_n=closed_n,
        total_trades_n=total_n,
        exports_blocked=exports_blocked,
    )


@bp.route("/users/<int:user_id>/exports", methods=["POST"])
@require_admin_link
def user_toggle_exports(user_id: int):
    u = User.query.get_or_404(user_id)
    block = request.form.get("exports_blocked") == "1"
    try:
        u.exports_blocked = block
        db.session.commit()
        log_admin_event(
            db,
            "user_exports_toggle",
            {"user_id": user_id, "blocked": block},
            ip=_client_ip(),
        )
        flash("Export block updated." if block else "Exports re-enabled for user.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Could not update user: {exc}", "danger")
    return redirect(url_for("admin.user_inspect", user_id=user_id))


@bp.route("/export/users.csv")
@require_admin_link
def export_users_csv():
    ut = User.__table__
    rows = db.session.execute(
        select(ut.c.id, ut.c.username, ut.c.email, ut.c.created_at, ut.c.last_login).order_by(
            ut.c.id.asc()
        )
    ).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "username", "email", "created_at", "last_login"])
    for r in rows:
        w.writerow(
            [
                r.id,
                r.username or "",
                r.email or "",
                r.created_at.isoformat() if r.created_at else "",
                r.last_login.isoformat() if r.last_login else "",
            ]
        )
    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    mem.seek(0)
    return Response(
        mem.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=admin_users.csv"},
    )


@bp.route("/export/trades_recent.csv")
@require_admin_link
def export_trades_recent_csv():
    tt = Trade.__table__
    ut = User.__table__
    j = tt.outerjoin(ut, tt.c.user_id == ut.c.id)
    rows = db.session.execute(
        select(
            tt.c.id,
            tt.c.user_id,
            ut.c.username,
            tt.c.symbol,
            tt.c.status,
            tt.c.profit_loss,
            tt.c.created_at,
        )
        .select_from(j)
        .order_by(tt.c.created_at.desc())
        .limit(500)
    ).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "user_id", "username", "symbol", "status", "profit_loss", "created_at"])
    for r in rows:
        w.writerow(
            [
                r.id,
                r.user_id,
                r.username or "",
                r.symbol or "",
                r.status or "",
                r.profit_loss if r.profit_loss is not None else "",
                r.created_at.isoformat() if r.created_at else "",
            ]
        )
    return Response(
        buf.getvalue().encode("utf-8"),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=admin_trades_recent.csv"},
    )


@bp.route("/email/preview", methods=["POST"])
@require_admin_link
def email_preview():
    cfg = current_app.config
    app_name = cfg.get("APP_NAME", "TradeVerse")
    login_url = url_for("auth.login", _external=True)
    body_tpl = (request.form.get("body") or "").strip()
    audience = (request.form.get("audience") or "all_registered").strip()
    inactive_days = int(request.form.get("inactive_days") or 14)

    sample = None
    try:
        if audience == "test_self":
            sample = User.query.filter(User.email.isnot(None)).first()
        elif audience == "all_registered":
            cand = audience_users(audience="all_registered", inactive_days=inactive_days)
            if cand:
                sample = random.choice(cand)
        elif audience == "inactive":
            cand = audience_users(audience="inactive", inactive_days=inactive_days)
            if cand:
                sample = random.choice(cand)
    except Exception:
        sample = None
    if sample is None:
        sample = User.query.filter(User.email.isnot(None)).first()
    if sample is None:
        sample = SimpleNamespace(username="demo_trader", email="trader@example.com")

    rendered = apply_email_placeholders(
        body_tpl or "(empty body)",
        user=sample,
        app_name=app_name,
        login_url=login_url,
    )
    label = getattr(sample, "email", "") or getattr(sample, "username", "")
    return Response(
        json.dumps(
            {
                "sample_label": label,
                "body": rendered,
            }
        ),
        mimetype="application/json",
    )


@bp.route("/email/draft", methods=["POST"])
@require_admin_link
def email_draft_save():
    name = (request.form.get("draft_name") or "").strip()[:120]
    subject = (request.form.get("draft_subject") or "").strip()[:200]
    body = (request.form.get("draft_body") or "").strip()
    aud = (request.form.get("draft_audience") or "test_self").strip()[:40]
    if not name:
        flash("Draft name is required.", "warning")
        return redirect(url_for("admin.email_outreach"))
    try:
        d = AdminEmailDraft(name=name, subject=subject, body=body, audience_hint=aud)
        db.session.add(d)
        db.session.commit()
        log_admin_event(db, "email_draft_save", {"id": d.id, "name": name}, ip=_client_ip())
        flash(f"Saved draft “{name}”.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Could not save draft: {exc}", "danger")
    return redirect(url_for("admin.email_outreach"))


@bp.route("/email/draft/<int:draft_id>/delete", methods=["POST"])
@require_admin_link
def email_draft_delete(draft_id: int):
    try:
        d = AdminEmailDraft.query.get_or_404(draft_id)
        db.session.delete(d)
        db.session.commit()
        log_admin_event(db, "email_draft_delete", {"id": draft_id}, ip=_client_ip())
        flash("Draft deleted.", "info")
    except Exception as exc:
        db.session.rollback()
        flash(f"Could not delete: {exc}", "danger")
    return redirect(url_for("admin.email_outreach"))


@bp.route("/email", methods=["GET", "POST"])
@require_admin_link
def email_outreach():
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
        bulk_phrase = (request.form.get("bulk_phrase") or "").strip()

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
                log_admin_event(
                    db,
                    "email_test",
                    {"to": test_email},
                    ip=_client_ip(),
                )
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
            code = _bulk_challenge_code()
            expected = f"SEND {code}" if code else None
            if not expected or bulk_phrase != expected:
                flash(
                    "Bulk send blocked: type the confirmation phrase exactly (see hint on this page).",
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

            log_admin_event(
                db,
                "email_bulk",
                {
                    "audience": audience,
                    "sent": sent,
                    "failed": failed,
                    "truncated": truncated,
                    "inactive_days": inactive_days,
                },
                ip=_client_ip(),
            )

            parts = [f"Finished: {sent} sent", f"{failed} failed."]
            if truncated:
                parts.append(
                    f"Capped at {max_per_run} recipients per run (set OWNER_EMAIL_MAX_PER_RUN to raise)."
                )
            flash(" ".join(parts), "success" if failed == 0 else "warning")
            _refresh_bulk_challenge()
            return redirect(url_for("admin.email_outreach"))

        flash("Unknown audience selection.", "danger")
        return redirect(url_for("admin.email_outreach"))

    activity = func.coalesce(User.last_login, User.created_at)
    cutoff = utc_now() - timedelta(days=inactive_default)
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

    bulk_code = _refresh_bulk_challenge()
    drafts = []
    try:
        drafts = AdminEmailDraft.query.order_by(AdminEmailDraft.id.desc()).limit(25).all()
    except Exception:
        drafts = []

    emails_today = count_admin_emails_today(db)

    return render_template(
        "admin/email_outreach.html",
        mail_configured=mail_ok,
        app_name=app_name,
        login_url=login_url,
        recipient_count_all=n_all,
        recipient_count_inactive=n_inactive,
        inactive_days_default=inactive_default,
        max_per_run=max_per_run,
        bulk_code=bulk_code,
        drafts=drafts,
        emails_sent_today=emails_today,
        owner_email_cap=max_per_run,
    )
