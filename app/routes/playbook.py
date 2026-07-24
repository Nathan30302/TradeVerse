"""
Playbook routes.

Users save setups (rules + checklist + example images) and link them when logging trades
so they follow a defined strategy instead of trading blindly.
"""

from __future__ import annotations

import os
import uuid

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import case, func
from werkzeug.utils import secure_filename

from app import db
from app.models.playbook_setup import PlaybookSetup
from app.models.trade import Trade
from app.services.retention import setup_letter_grade
from app.services.strategy_lab import PLAYBOOK_STARTERS
from app.services.playbook_grades import (
    SETUP_GRADE_OPTIONS,
    focus_summary,
    grade_coach_note,
    is_focus_grade,
)
from app.services.uploads_storage import playbook_images_dir, resolve_playbook_file


bp = Blueprint("playbook", __name__, url_prefix="/playbook")

_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}
_MAX_IMAGES = 6
_MAX_IMAGE_BYTES = 5 * 1024 * 1024


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


def _unlink_playbook_image(stored_path: str) -> None:
    if not stored_path or not stored_path.startswith("uploads/playbook/"):
        return
    fname = stored_path.split("/", 2)[-1]
    found = resolve_playbook_file(fname)
    if not found:
        return
    folder, name = found
    try:
        os.remove(os.path.join(folder, name))
    except OSError:
        current_app.logger.debug("playbook image unlink failed", exc_info=True)


def _save_uploaded_playbook_images(user_id: int, storages) -> list[str]:
    """Validate and persist uploaded example images; return relative paths."""
    saved: list[str] = []
    dest_dir = playbook_images_dir()
    os.makedirs(dest_dir, exist_ok=True)

    for storage in storages or []:
        if not storage or not getattr(storage, "filename", None):
            continue
        if len(saved) >= _MAX_IMAGES:
            break
        raw = storage.filename
        ext = raw.rsplit(".", 1)[-1].lower() if "." in raw else ""
        if ext not in _IMAGE_EXTS:
            flash(f"Skipped {raw}: use PNG, JPG, GIF, or WebP.", "warning")
            continue
        try:
            storage.seek(0)
        except Exception:
            pass
        data = storage.read(_MAX_IMAGE_BYTES + 1)
        if not data:
            continue
        if len(data) > _MAX_IMAGE_BYTES:
            flash(f"Skipped {raw}: larger than 5 MB.", "warning")
            continue
        out_name = f"u{user_id}_{uuid.uuid4().hex[:16]}.{ext}"
        safe = secure_filename(out_name)
        if not safe or safe != out_name:
            continue
        full = os.path.join(dest_dir, safe)
        try:
            with open(full, "wb") as out_f:
                out_f.write(data)
        except OSError:
            current_app.logger.warning("playbook image save failed", exc_info=True)
            flash("Could not save one of the images. Try again.", "warning")
            continue
        saved.append(f"uploads/playbook/{safe}")
    return saved


def _apply_example_images_from_request(setup: PlaybookSetup) -> None:
    """Merge keep/remove checkboxes with newly uploaded files."""
    existing = setup.example_image_list()
    remove = set(request.form.getlist("remove_image") or [])
    kept = [p for p in existing if p not in remove]
    for path in existing:
        if path in remove:
            _unlink_playbook_image(path)

    room = max(0, _MAX_IMAGES - len(kept))
    uploads = request.files.getlist("example_images") if room else []
    if room and uploads:
        kept.extend(_save_uploaded_playbook_images(current_user.id, uploads)[:room])
    setup.set_example_image_list(kept)


def _form_to_setup_fields(setup: PlaybookSetup) -> str | None:
    """Apply POST fields onto setup. Returns error message or None."""
    from app.services.playbook_grades import normalize_setup_grade, parse_typical_rr

    name = (request.form.get("name") or "").strip()
    if not name:
        return "Name is required."
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

    grade = normalize_setup_grade(request.form.get("setup_grade"))
    setup.setup_grade = grade
    rr = parse_typical_rr(request.form.get("typical_rr"), grade=grade)
    if (request.form.get("typical_rr") or "").strip() and rr is None:
        return "Typical R:R must be a positive number (for example 2.5)."
    setup.typical_rr = rr
    return None


def _grade_badge_color(grade: str) -> str:
    g = (grade or "").upper()
    if g in ("A++", "A+"):
        return "success"
    if g in ("A-", "B+"):
        return "primary"
    if g in ("B-",):
        return "warning"
    if g in ("C",):
        return "secondary"
    return "secondary"


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

    return render_template(
        "playbook/index.html",
        setups=setups,
        stats_by_setup=stats_by_setup,
        starters=PLAYBOOK_STARTERS,
        focus_summary=focus_summary(setups),
        grade_badge_color=_grade_badge_color,
    )


@bp.route("/from-starter/<key>", methods=["POST"])
@login_required
def from_starter(key: str):
    """Create a playbook setup from a curated starter template."""
    if not _playbook_ready():
        return _playbook_unavailable_response()

    tmpl = next((t for t in PLAYBOOK_STARTERS if t.get("key") == key), None)
    if not tmpl:
        flash("Unknown starter template.", "warning")
        return redirect(url_for("playbook.index"))

    setup = PlaybookSetup(
        user_id=current_user.id,
        name=tmpl["name"],
        market=tmpl.get("market") or "",
        symbol_hint=tmpl.get("symbol_hint") or "",
        timeframe=tmpl.get("timeframe") or "",
        entry_criteria=tmpl.get("entry_criteria") or "",
        invalidation=tmpl.get("invalidation") or "",
        management_plan=tmpl.get("management_plan") or "",
        checklist_text=tmpl.get("checklist_text") or "",
        tags=tmpl.get("tags") or "",
        is_active=True,
        example_images="[]",
    )
    db.session.add(setup)
    db.session.commit()
    flash("Starter playbook saved — edit it to match your edge and add example charts.", "success")
    return redirect(url_for("playbook.edit", setup_id=setup.id))


def _grade_form_context():
    return {
        "setup_grade_options": SETUP_GRADE_OPTIONS,
        "is_focus_grade": is_focus_grade,
        "grade_coach_note": grade_coach_note,
        "grade_badge_color": _grade_badge_color,
    }


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if not _playbook_ready():
        return _playbook_unavailable_response()
    ctx = _grade_form_context()
    if request.method == "GET":
        return render_template("playbook/new.html", setup=None, **ctx)

    setup = PlaybookSetup(user_id=current_user.id, example_images="[]")
    err = _form_to_setup_fields(setup)
    if err:
        flash(err, "warning")
        return render_template("playbook/new.html", setup=setup, **ctx)

    _apply_example_images_from_request(setup)
    db.session.add(setup)
    db.session.commit()
    flash("Playbook setup saved. Select it when you log a trade so you stick to the plan.", "success")
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
        **_grade_form_context(),
    )


@bp.route("/<int:setup_id>/edit", methods=["GET", "POST"])
@login_required
def edit(setup_id: int):
    if not _playbook_ready():
        return _playbook_unavailable_response()
    setup = _get_setup_or_404(setup_id)
    ctx = _grade_form_context()
    if request.method == "GET":
        return render_template("playbook/edit.html", setup=setup, **ctx)

    err = _form_to_setup_fields(setup)
    if err:
        flash(err, "warning")
        return render_template("playbook/edit.html", setup=setup, **ctx)

    _apply_example_images_from_request(setup)
    db.session.commit()
    flash("Playbook setup updated.", "success")
    return redirect(url_for("playbook.view", setup_id=setup.id))


@bp.route("/<int:setup_id>/delete", methods=["POST"])
@login_required
def delete(setup_id: int):
    if not _playbook_ready():
        return _playbook_unavailable_response()
    setup = _get_setup_or_404(setup_id)
    for path in setup.example_image_list():
        _unlink_playbook_image(path)
    # Unlink trades so FK delete does not fail
    Trade.query.filter_by(user_id=current_user.id, playbook_setup_id=setup.id).update(
        {Trade.playbook_setup_id: None},
        synchronize_session=False,
    )
    db.session.delete(setup)
    db.session.commit()
    flash("Playbook setup deleted.", "info")
    return redirect(url_for("playbook.index"))
