"""
Stripe webhook event ledger for idempotency.

Stripe may retry webhook delivery. We store processed event IDs to prevent
duplicate subscription transitions.
"""

from __future__ import annotations

from datetime import datetime

from app import db


class StripeWebhookEvent(db.Model):
    __tablename__ = "stripe_webhook_events"

    id = db.Column(db.Integer, primary_key=True)
    stripe_event_id = db.Column(db.String(255), nullable=False, unique=True, index=True)
    event_type = db.Column(db.String(100), nullable=True)
    processed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

