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

    # JSON list of relative paths, e.g. ["uploads/playbook/u1_abc.png", ...]
    example_images = db.Column(db.Text, nullable=False, default="[]")

    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    def checklist_items(self) -> list[str]:
        return [x.strip() for x in (self.checklist_text or "").splitlines() if x.strip()]

    def example_image_list(self) -> list[str]:
        """Parsed list of stored example image paths (empty if unset/invalid)."""
        import json

        raw = (self.example_images or "").strip() or "[]"
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        out: list[str] = []
        for item in data:
            s = str(item or "").strip()
            if s and ".." not in s and s.startswith("uploads/playbook/"):
                out.append(s)
        return out

    def set_example_image_list(self, paths: list[str]) -> None:
        import json

        clean = []
        for item in paths or []:
            s = str(item or "").strip()
            if s and ".." not in s and s.startswith("uploads/playbook/"):
                clean.append(s)
        self.example_images = json.dumps(clean[:8])

