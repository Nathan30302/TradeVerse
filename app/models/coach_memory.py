"""
Coach Memory Model — long-term AI Coach observations per user.
"""

from __future__ import annotations

from app import db
from app.utils.timeutil import utc_now


class CoachMemory(db.Model):
    """Stores coaching observations so the mentor can build on past guidance."""

    __tablename__ = "coach_memories"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    kind = db.Column(db.String(40), nullable=False, default="note")  # leak|focus|improvement|chat|grade
    title = db.Column(db.String(200), nullable=False, default="")
    body = db.Column(db.Text, nullable=False, default="")
    meta_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
