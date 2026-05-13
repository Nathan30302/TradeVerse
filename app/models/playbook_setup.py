"""
Trading Playbook models.

A playbook is a user's curated set of setups/rules/checklists they aim to execute.
"""

from __future__ import annotations

from app.utils.timeutil import utc_now

from app import db


class PlaybookSetup(db.Model):
    __tablename__ = "playbook_setups"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    name = db.Column(db.String(140), nullable=False, default="")
    market = db.Column(db.String(40), nullable=False, default="")  # e.g. Forex / Indices / Crypto
    symbol_hint = db.Column(db.String(40), nullable=False, default="")  # optional: e.g. XAUUSD
    timeframe = db.Column(db.String(16), nullable=False, default="")  # e.g. 15M / 1H

    entry_criteria = db.Column(db.Text, nullable=False, default="")
    invalidation = db.Column(db.Text, nullable=False, default="")
    management_plan = db.Column(db.Text, nullable=False, default="")
    checklist_text = db.Column(db.Text, nullable=False, default="")  # one item per line

    tags = db.Column(db.String(180), nullable=False, default="")  # comma-separated
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    def checklist_items(self) -> list[str]:
        return [x.strip() for x in (self.checklist_text or "").splitlines() if x.strip()]

