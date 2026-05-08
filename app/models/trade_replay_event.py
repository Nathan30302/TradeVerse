"""
Trade Replay models.

Replay turns each trade into a step-by-step timeline: screenshots + notes + key moments.
"""

from __future__ import annotations

from datetime import datetime

from app import db


class TradeReplayEvent(db.Model):
    __tablename__ = "trade_replay_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    trade_id = db.Column(db.Integer, db.ForeignKey("trades.id"), nullable=False, index=True)

    event_type = db.Column(db.String(20), nullable=False, default="note")  # before/entry/manage/exit/review/note
    occurred_at = db.Column(db.DateTime, nullable=True, index=True)  # optional: when it happened

    note = db.Column(db.Text, nullable=False, default="")

    media_filename = db.Column(db.String(255), nullable=True)  # stored on disk
    media_mimetype = db.Column(db.String(80), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

