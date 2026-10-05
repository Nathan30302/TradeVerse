"""
Owner-only trading rulebooks & strategies — Nathan's personal discipline system.
"""

from __future__ import annotations

from app import db
from app.utils.timeutil import utc_now


class OwnerRulebook(db.Model):
    """Account-level desk settings (one per owner): equity, unlock, daily counters."""

    __tablename__ = "owner_rulebooks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True, index=True)

    # Legacy single-bible fields kept for compatibility; strategies hold the real playbooks.
    strategy_name = db.Column(db.String(160), nullable=False, default="My system")
    overview = db.Column(db.Text, nullable=True)
    markets = db.Column(db.Text, nullable=True)
    timeframes = db.Column(db.String(120), nullable=True)
    weekly_bias_rules = db.Column(db.Text, nullable=True)
    daily_bias_rules = db.Column(db.Text, nullable=True)
    h4_rules = db.Column(db.Text, nullable=True)
    m15_rules = db.Column(db.Text, nullable=True)
    entry_rules = db.Column(db.Text, nullable=True)
    exit_rules = db.Column(db.Text, nullable=True)
    invalidation_rules = db.Column(db.Text, nullable=True)
    do_not_trade_rules = db.Column(db.Text, nullable=True)
    psychology_rules = db.Column(db.Text, nullable=True)
    session_windows_json = db.Column(db.Text, nullable=False, default="[]")
    gate_strict = db.Column(db.Boolean, nullable=False, default=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    account_starting_balance = db.Column(db.Float, nullable=True)
    account_high_water = db.Column(db.Float, nullable=True)
    account_current_balance = db.Column(db.Float, nullable=True)
    risk_base_pct = db.Column(db.Float, nullable=False, default=1.0)
    risk_min_pct = db.Column(db.Float, nullable=False, default=0.25)
    max_trades_per_day = db.Column(db.Integer, nullable=True)
    max_losses_in_row = db.Column(db.Integer, nullable=True)

    unlocked_date = db.Column(db.String(10), nullable=True)
    unlocked_note = db.Column(db.String(255), nullable=True)

    active_strategy_id = db.Column(db.Integer, nullable=True)
    day_key = db.Column(db.String(10), nullable=True)  # local YYYY-MM-DD for counters
    trades_today = db.Column(db.Integer, nullable=False, default=0)
    wins_today = db.Column(db.Integer, nullable=False, default=0)
    losses_today = db.Column(db.Integer, nullable=False, default=0)
    day_locked = db.Column(db.Boolean, nullable=False, default=False)
    day_lock_reason = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class OwnerStrategy(db.Model):
    """One of Nathan's named trading systems (multi-strategy library)."""

    __tablename__ = "owner_strategies"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    slug = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    tagline = db.Column(db.String(255), nullable=True)
    style = db.Column(db.String(120), nullable=True)
    overview = db.Column(db.Text, nullable=True)
    markets = db.Column(db.Text, nullable=True)
    instruments_json = db.Column(db.Text, nullable=True)
    timeframes = db.Column(db.String(160), nullable=True)
    timezone_name = db.Column(db.String(64), nullable=False, default="America/New_York")

    weekly_bias_rules = db.Column(db.Text, nullable=True)
    daily_bias_rules = db.Column(db.Text, nullable=True)
    h4_rules = db.Column(db.Text, nullable=True)
    m15_rules = db.Column(db.Text, nullable=True)
    entry_rules = db.Column(db.Text, nullable=True)
    exit_rules = db.Column(db.Text, nullable=True)
    invalidation_rules = db.Column(db.Text, nullable=True)
    do_not_trade_rules = db.Column(db.Text, nullable=True)
    psychology_rules = db.Column(db.Text, nullable=True)

    session_windows_json = db.Column(db.Text, nullable=False, default="[]")
    checklist_json = db.Column(db.Text, nullable=True)
    spec_json = db.Column(db.Text, nullable=True)

    gate_strict = db.Column(db.Boolean, nullable=False, default=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    stop_after_first_win = db.Column(db.Boolean, nullable=False, default=True)
    max_trades_per_day = db.Column(db.Integer, nullable=False, default=2)
    max_losses_in_row = db.Column(db.Integer, nullable=True)
    risk_base_pct = db.Column(db.Float, nullable=False, default=1.0)
    risk_min_pct = db.Column(db.Float, nullable=False, default=0.25)
    min_rr = db.Column(db.Float, nullable=False, default=2.0)
    target_rr = db.Column(db.Float, nullable=False, default=4.0)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "slug", name="uq_owner_strategies_user_slug"),
    )


class OwnerRuleCheckLog(db.Model):
    """Audit: blocked trades, unlocks, advice acknowledgements."""

    __tablename__ = "owner_rule_check_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    event_type = db.Column(db.String(40), nullable=False)
    detail = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
