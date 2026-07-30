"""
Coach goals and challenges — measurable habits the AI Coach tracks.
"""

from __future__ import annotations

from datetime import timedelta

from app import db
from app.utils.timeutil import utc_now


class CoachGoal(db.Model):
    """User-defined measurable coaching goal."""

    __tablename__ = "coach_goals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False, default="")
    metric = db.Column(db.String(40), nullable=False, default="custom")
    # rule_adherence | max_trades_day | risk_pct | no_revenge | journal_days | custom
    target_value = db.Column(db.Float, nullable=True)
    target_text = db.Column(db.String(400), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="active")  # active|completed|paused
    progress_pct = db.Column(db.Float, nullable=False, default=0.0)
    progress_detail = db.Column(db.String(400), nullable=False, default="")
    starts_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)


class CoachChallenge(db.Model):
    """Time-boxed coaching challenge with completion review."""

    __tablename__ = "coach_challenges"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    code = db.Column(db.String(40), nullable=False, default="")
    title = db.Column(db.String(200), nullable=False, default="")
    description = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="active")  # active|completed|failed|abandoned
    target_count = db.Column(db.Integer, nullable=False, default=5)
    progress_count = db.Column(db.Integer, nullable=False, default=0)
    progress_detail = db.Column(db.String(400), nullable=False, default="")
    review_text = db.Column(db.Text, nullable=False, default="")
    starts_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)


CHALLENGE_CATALOG = [
    {
        "code": "no_sl_move",
        "title": "Five trades without moving stop loss",
        "description": "Complete 5 closed trades. Do not move SL farther from price after entry (log honest notes).",
        "target_count": 5,
        "days": 14,
    },
    {
        "code": "journal_7",
        "title": "Seven days of journaling",
        "description": "Log or review at least one trade note on 7 distinct days.",
        "target_count": 7,
        "days": 14,
    },
    {
        "code": "risk_1pct",
        "title": "Ten trades at ~1% risk",
        "description": "Close 10 trades with risk percentage near 1% (0.75–1.25%).",
        "target_count": 10,
        "days": 21,
    },
    {
        "code": "no_revenge",
        "title": "One week with no emotional rule breaks",
        "description": "Seven days without Revenge/FOMO/tilt emotion tags on closed trades.",
        "target_count": 7,
        "days": 7,
    },
    {
        "code": "max_two",
        "title": "Max two trades per day for 5 days",
        "description": "On 5 trading days, take at most 2 closed trades each day.",
        "target_count": 5,
        "days": 14,
    },
]
