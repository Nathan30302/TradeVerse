"""
AI Coaching Note Model
Stores pinned coaching rules + checklists for premium AI Buddy workflows.
"""

from __future__ import annotations

from datetime import datetime

from app import db


class AICoachingNote(db.Model):
    __tablename__ = "ai_coaching_notes"

    # ==================== Primary Key ====================
    id = db.Column(db.Integer, primary_key=True)

    # ==================== Foreign Keys ====================
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    # ==================== Content ====================
    pinned_rule = db.Column(db.Text, nullable=False, default="")
    checklist_text = db.Column(db.Text, nullable=False, default="")  # one item per line
    source = db.Column(db.String(30), nullable=False, default="manual")  # manual | trade_doctor | ai
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # ==================== Timestamps ====================
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def checklist_items(self) -> list[str]:
        return [x.strip() for x in (self.checklist_text or "").splitlines() if x.strip()]

