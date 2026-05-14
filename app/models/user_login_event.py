"""Append-only login audit rows for account activity views."""

from app import db
from app.utils.timeutil import utc_now


class UserLoginEvent(db.Model):
    """One row per successful password login (best-effort insert)."""

    __tablename__ = "user_login_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    occurred_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(512), nullable=True)
