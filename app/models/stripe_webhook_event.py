"""
Stripe webhook event ledger for idempotency.

Stripe may retry webhook delivery. We store processed event IDs to prevent
duplicate subscription transitions.
"""

from __future__ import annotations

from app import db
from app.utils.timeutil import utc_now


class StripeWebhookEvent(db.Model):
    __tablename__ = "stripe_webhook_events"

    id = db.Column(db.Integer, primary_key=True)
    stripe_event_id = db.Column(db.String(255), nullable=False, unique=True, index=True)
    event_type = db.Column(db.String(100), nullable=True)
    processed_at = db.Column(db.DateTime, default=utc_now, nullable=False)

