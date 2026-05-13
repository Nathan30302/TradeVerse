"""
Admin console persistence: audit trail, email drafts, rate-limit accounting.
"""

from __future__ import annotations

from app import db
from app.utils.timeutil import utc_now


class AdminConsoleEvent(db.Model):
    """Structured audit / telemetry events from token-gated admin actions."""

    __tablename__ = "admin_console_events"

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(40), nullable=False, index=True)
    meta_json = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)


class AdminEmailDraft(db.Model):
    """Saved email outreach templates."""

    __tablename__ = "admin_email_drafts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200), nullable=False, default="")
    body = db.Column(db.Text, nullable=False, default="")
    audience_hint = db.Column(db.String(40), default="test_self")
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
