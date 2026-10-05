"""
Owner-only trading rulebook — Nathan's personal discipline system (not public).
"""

from __future__ import annotations

from app import db
from app.utils.timeutil import utc_now


class OwnerRulebook(db.Model):
    """Detailed personal strategy bible for the platform owner."""

    __tablename__ = "owner_rulebooks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True, index=True)

    strategy_name = db.Column(db.String(160), nullable=False, default="My system")
    overview = db.Column(db.Text, nullable=True)

    markets = db.Column(db.Text, nullable=True)  # free text / comma list
    timeframes = db.Column(db.String(120), nullable=True)  # e.g. W, D, H4, M15

    # Core rule sections (plain language Nathan writes)
    weekly_bias_rules = db.Column(db.Text, nullable=True)
    daily_bias_rules = db.Column(db.Text, nullable=True)
    h4_rules = db.Column(db.Text, nullable=True)
    m15_rules = db.Column(db.Text, nullable=True)
    entry_rules = db.Column(db.Text, nullable=True)
    exit_rules = db.Column(db.Text, nullable=True)
    invalidation_rules = db.Column(db.Text, nullable=True)
    do_not_trade_rules = db.Column(db.Text, nullable=True)
    psychology_rules = db.Column(db.Text, nullable=True)

    # Session windows JSON: [{"label","days":[0-6],"start":"HH:MM","end":"HH:MM"}]
    session_windows_json = db.Column(db.Text, nullable=False, default="[]")
    gate_strict = db.Column(db.Boolean, nullable=False, default=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    # Risk — scales down in drawdown from high-water mark
    account_starting_balance = db.Column(db.Float, nullable=True)
    account_high_water = db.Column(db.Float, nullable=True)
    account_current_balance = db.Column(db.Float, nullable=True)
    risk_base_pct = db.Column(db.Float, nullable=False, default=1.0)
    risk_min_pct = db.Column(db.Float, nullable=False, default=0.25)
    max_trades_per_day = db.Column(db.Integer, nullable=True)
    max_losses_in_row = db.Column(db.Integer, nullable=True)

    # Soft unlock for today (YYYY-MM-DD) when he explicitly opens the session desk
    unlocked_date = db.Column(db.String(10), nullable=True)
    unlocked_note = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class OwnerRuleCheckLog(db.Model):
    """Audit: blocked trades, unlocks, advice acknowledgements."""

    __tablename__ = "owner_rule_check_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    event_type = db.Column(db.String(40), nullable=False)
    # blocked_outside_hours | unlocked_session | risk_advice | rule_warning | balance_update
    detail = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
