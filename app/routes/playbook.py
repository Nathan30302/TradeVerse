"""
Playbook routes.

MVP: users can save and iterate on a small set of setups with a checklist.
"""

from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.playbook_setup import PlaybookSetup
from app.models.trade import Trade
from app.services.retention import setup_letter_grade
from sqlalchemy import case, func


bp = Blueprint("playbook", __name__, url_prefix="/playbook")


def _playbook_ready() -> bool:
    return bool(current_app.extensions.get("tradeverse_schema", {}).get("playbook_ready"))


def _playbook_unavailable_response():
    flash(
        "Playbook is not available yet. Run `flask db upgrade` to enable setup tracking.",
        "warning",
    )
    return redirect(url_for("dashboard.index"))


def _get_setup_or_404(setup_id: int) -> PlaybookSetup:
    setup = PlaybookSetup.query.filter_by(id=setup_id, user_id=current_user.id).first()
    if not setup:
        abort(404)
    return setup


@bp.route("/")
@login_required
def index():
    if not _playbook_ready():
        return _playbook_unavailable_response()
    setups = (
        PlaybookSetup.query.filter_by(user_id=current_user.id)
        .order_by(PlaybookSetup.updated_at.desc().nullslast(), PlaybookSetup.created_at.desc())
        .all()
    )
    setup_ids = [s.id for s in setups]
    stats_by_setup = {}
    if setup_ids:
        rows = (
            db.session.query(
                Trade.playbook_setup_id,
                func.count(Trade.id),
                func.coalesce(func.sum(Trade.profit_loss), 0.0),
                func.coalesce(func.sum(case((Trade.profit_loss > 0, 1), else_=0)), 0),
                func.coalesce(func.sum(case((Trade.profit_loss < 0, 1), else_=0)), 0),
                func.coalesce(func.avg(Trade.risk_reward), 0.0),
            )
            .filter(Trade.user_id == current_user.id, Trade.playbook_setup_id.in_(setup_ids))
            .group_by(Trade.playbook_setup_id)
            .all()
        )
        for setup_id, count, pnl, wins, losses, avg_rr in rows:
            total = int(wins or 0) + int(losses or 0)
            wr = (float(wins) / total * 100.0) if total else 0.0
            grade, grade_color = setup_letter_grade(wr, int(count or 0), float(avg_rr or 0.0))
            stats_by_setup[int(setup_id)] = {
                "count": int(count or 0),
                "pnl": float(pnl or 0.0),
                "wins": int(wins or 0),
                "losses": int(losses or 0),
                "win_rate": float(wr),
                "avg_rr": float(avg_rr or 0.0),
                "grade": grade,
                "grade_color": grade_color,
            }

    return render_template("playbook/index.html", setups=setups, stats_by_setup=stats_by_setup)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if not _playbook_ready():
        return _playbook_unavailable_response()
    if request.method == "GET":
        return render_template("playbook/new.html")

    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Name is required.", "warning")
        return render_template("playbook/new.html")

    setup = PlaybookSetup(
        user_id=current_user.id,
        name=name,
        market=(request.form.get("market") or "").strip(),
        symbol_hint=(request.form.get("symbol_hint") or "").strip(),
        timeframe=(request.form.get("timeframe") or "").strip(),
        entry_criteria=(request.form.get("entry_criteria") or "").strip(),
        invalidation=(request.form.get("invalidation") or "").strip(),
        management_plan=(request.form.get("management_plan") or "").strip(),
        checklist_text=(request.form.get("checklist_text") or "").strip(),
        tags=(request.form.get("tags") or "").strip(),
        is_active=(request.form.get("is_active") or "").lower() in ("1", "true", "yes", "on"),
    )
    db.session.add(setup)
    db.session.commit()
    flash("Playbook setup saved.", "success")
    return redirect(url_for("playbook.view", setup_id=setup.id))


@bp.route("/<int:setup_id>")
@login_required
def view(setup_id: int):
    if not _playbook_ready():
        return _playbook_unavailable_response()
    setup = _get_setup_or_404(setup_id)
    trades = (
        Trade.query.filter_by(user_id=current_user.id, playbook_setup_id=setup.id)
        .order_by(Trade.entry_date.desc())
        .limit(30)
        .all()
    )
    # lightweight stats for header
    pnl = sum([(t.profit_loss or 0.0) for t in trades]) if trades else 0.0
    wins = len([t for t in trades if (t.profit_loss or 0) > 0])
    losses = len([t for t in trades if (t.profit_loss or 0) < 0])
    total = wins + losses
    win_rate = (wins / total * 100.0) if total else 0.0
    avg_rr = (
        sum([(t.risk_reward or 0.0) for t in trades]) / len(trades) if trades else 0.0
    )
    grade, grade_color = setup_letter_grade(win_rate, len(trades), avg_rr)
    return render_template(
        "playbook/view.html",
        setup=setup,
        trades=trades,
        setup_stats={
            "count": len(trades),
            "pnl": pnl,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "avg_rr": avg_rr,
            "grade": grade,
            "grade_color": grade_color,
        },
    )


@bp.route("/<int:setup_id>/edit", methods=["GET", "POST"])
@login_required
def edit(setup_id: int):
    if not _playbook_ready():
        return _playbook_unavailable_response()
    setup = _get_setup_or_404(setup_id)
    if request.method == "GET":
        return render_template("playbook/edit.html", setup=setup)

    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Name is required.", "warning")
        return render_template("playbook/edit.html", setup=setup)

    setup.name = name
    setup.market = (request.form.get("market") or "").strip()
    setup.symbol_hint = (request.form.get("symbol_hint") or "").strip()
    setup.timeframe = (request.form.get("timeframe") or "").strip()
    setup.entry_criteria = (request.form.get("entry_criteria") or "").strip()
    setup.invalidation = (request.form.get("invalidation") or "").strip()
    setup.management_plan = (request.form.get("management_plan") or "").strip()
    setup.checklist_text = (request.form.get("checklist_text") or "").strip()
    setup.tags = (request.form.get("tags") or "").strip()
    setup.is_active = (request.form.get("is_active") or "").lower() in ("1", "true", "yes", "on")

    db.session.commit()
    flash("Playbook setup updated.", "success")
    return redirect(url_for("playbook.view", setup_id=setup.id))


@bp.route("/<int:setup_id>/delete", methods=["POST"])
@login_required
def delete(setup_id: int):
    if not _playbook_ready():
        return _playbook_unavailable_response()
    setup = _get_setup_or_404(setup_id)
    db.session.delete(setup)
    db.session.commit()
    flash("Playbook setup deleted.", "info")
    return redirect(url_for("playbook.index"))

