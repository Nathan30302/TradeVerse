"""
Trade Replay routes.

Replay is a timeline for a single trade: notes + screenshots across key moments.
"""

from __future__ import annotations

import os

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app import db
from app.models.trade import Trade
from app.models.trade_replay_event import TradeReplayEvent
from app.utils.timeutil import utc_now, parse_datetime_optional


bp = Blueprint("replay", __name__, url_prefix="/replay")


def _allowed_file(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in (current_app.config.get("ALLOWED_EXTENSIONS") or set())


def _replay_upload_dir() -> str:
    base = current_app.config.get("TRADE_SCREENSHOTS_FOLDER") or current_app.config.get("UPLOAD_FOLDER") or "/tmp"
    path = os.path.join(base, "replay")
    os.makedirs(path, exist_ok=True)
    return path


def _trade_or_404(trade_id: int) -> Trade:
    t = Trade.query.filter_by(id=trade_id, user_id=current_user.id).first()
    if not t:
        abort(404)
    return t


@bp.route("/")
@login_required
def index():
    trades = (
        Trade.query.filter_by(user_id=current_user.id)
        .order_by(Trade.entry_date.desc())
        .limit(60)
        .all()
    )
    return render_template("replay/index.html", trades=trades)


@bp.route("/trade/<int:trade_id>")
@login_required
def trade_replay(trade_id: int):
    trade = _trade_or_404(trade_id)
    events = (
        TradeReplayEvent.query.filter_by(user_id=current_user.id, trade_id=trade.id)
        .order_by(TradeReplayEvent.occurred_at.asc().nulls_last(), TradeReplayEvent.created_at.asc())
        .all()
    )
    return render_template("replay/trade.html", trade=trade, events=events)


@bp.route("/trade/<int:trade_id>/add", methods=["POST"])
@login_required
def add_event(trade_id: int):
    trade = _trade_or_404(trade_id)

    event_type = (request.form.get("event_type") or "note").strip().lower()
    if event_type not in {"before", "entry", "manage", "exit", "review", "note"}:
        event_type = "note"

    note = (request.form.get("note") or "").strip()
    occurred_at_str = (request.form.get("occurred_at") or "").strip()
    occurred_at = parse_datetime_optional(occurred_at_str)

    media_filename = None
    media_mimetype = None
    f = request.files.get("media")
    if f and getattr(f, "filename", ""):
        if not _allowed_file(f.filename):
            flash("Unsupported file type.", "warning")
            return redirect(url_for("replay.trade_replay", trade_id=trade.id))
        safe = secure_filename(f.filename)
        ts = utc_now().strftime("%Y%m%d_%H%M%S")
        stored = f"u{current_user.id}_t{trade.id}_{ts}_{safe}"
        dst_dir = _replay_upload_dir()
        dest_path = os.path.join(dst_dir, stored)
        f.save(dest_path)
        try:
            if not os.path.isfile(dest_path) or os.path.getsize(dest_path) == 0:
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
                flash("Screenshot upload failed or file was empty.", "warning")
                return redirect(url_for("replay.trade_replay", trade_id=trade.id))
        except OSError:
            flash("Could not verify uploaded file.", "warning")
            return redirect(url_for("replay.trade_replay", trade_id=trade.id))
        media_filename = stored
        media_mimetype = f.mimetype

    if not note and not media_filename:
        flash("Add a note or upload a screenshot.", "warning")
        return redirect(url_for("replay.trade_replay", trade_id=trade.id))

    ev = TradeReplayEvent(
        user_id=current_user.id,
        trade_id=trade.id,
        event_type=event_type,
        occurred_at=occurred_at,
        note=note,
        media_filename=media_filename,
        media_mimetype=media_mimetype,
    )
    db.session.add(ev)
    db.session.commit()
    flash("Replay event added.", "success")
    return redirect(url_for("replay.trade_replay", trade_id=trade.id))


@bp.route("/media/<path:filename>")
@login_required
def media(filename: str):
    # Only allow serving media that belongs to the current user via an event record.
    exists = (
        TradeReplayEvent.query.filter_by(user_id=current_user.id, media_filename=filename)
        .limit(1)
        .first()
    )
    if not exists:
        abort(404)
    directory = _replay_upload_dir()
    return send_from_directory(directory, filename)

