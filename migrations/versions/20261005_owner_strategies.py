"""Owner strategies + desk daily counters.

Revision ID: 20261005_owner_strategies
Revises: 20261005_owner_rulebooks
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa


revision = "20261005_owner_strategies"
down_revision = "20261005_owner_rulebooks"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("owner_rulebooks"):
        cols = {c["name"] for c in insp.get_columns("owner_rulebooks")}
        additions = [
            ("active_strategy_id", sa.Column("active_strategy_id", sa.Integer(), nullable=True)),
            ("day_key", sa.Column("day_key", sa.String(length=10), nullable=True)),
            ("trades_today", sa.Column("trades_today", sa.Integer(), nullable=False, server_default="0")),
            ("wins_today", sa.Column("wins_today", sa.Integer(), nullable=False, server_default="0")),
            ("losses_today", sa.Column("losses_today", sa.Integer(), nullable=False, server_default="0")),
            ("day_locked", sa.Column("day_locked", sa.Boolean(), nullable=False, server_default=sa.false())),
            ("day_lock_reason", sa.Column("day_lock_reason", sa.String(length=255), nullable=True)),
        ]
        for name, col in additions:
            if name not in cols:
                op.add_column("owner_rulebooks", col)

    if not insp.has_table("owner_strategies"):
        op.create_table(
            "owner_strategies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("slug", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("tagline", sa.String(length=255), nullable=True),
            sa.Column("style", sa.String(length=120), nullable=True),
            sa.Column("overview", sa.Text(), nullable=True),
            sa.Column("markets", sa.Text(), nullable=True),
            sa.Column("instruments_json", sa.Text(), nullable=True),
            sa.Column("timeframes", sa.String(length=160), nullable=True),
            sa.Column("timezone_name", sa.String(length=64), nullable=False, server_default="America/New_York"),
            sa.Column("weekly_bias_rules", sa.Text(), nullable=True),
            sa.Column("daily_bias_rules", sa.Text(), nullable=True),
            sa.Column("h4_rules", sa.Text(), nullable=True),
            sa.Column("m15_rules", sa.Text(), nullable=True),
            sa.Column("entry_rules", sa.Text(), nullable=True),
            sa.Column("exit_rules", sa.Text(), nullable=True),
            sa.Column("invalidation_rules", sa.Text(), nullable=True),
            sa.Column("do_not_trade_rules", sa.Text(), nullable=True),
            sa.Column("psychology_rules", sa.Text(), nullable=True),
            sa.Column("session_windows_json", sa.Text(), nullable=False),
            sa.Column("checklist_json", sa.Text(), nullable=True),
            sa.Column("spec_json", sa.Text(), nullable=True),
            sa.Column("gate_strict", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("stop_after_first_win", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("max_trades_per_day", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("max_losses_in_row", sa.Integer(), nullable=True),
            sa.Column("risk_base_pct", sa.Float(), nullable=False, server_default="1"),
            sa.Column("risk_min_pct", sa.Float(), nullable=False, server_default="0.25"),
            sa.Column("min_rr", sa.Float(), nullable=False, server_default="2"),
            sa.Column("target_rr", sa.Float(), nullable=False, server_default="4"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", "slug", name="uq_owner_strategies_user_slug"),
        )
        op.create_index("ix_owner_strategies_user_id", "owner_strategies", ["user_id"])


def downgrade():
    op.drop_table("owner_strategies")
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("owner_rulebooks"):
        cols = {c["name"] for c in insp.get_columns("owner_rulebooks")}
        for name in (
            "day_lock_reason",
            "day_locked",
            "losses_today",
            "wins_today",
            "trades_today",
            "day_key",
            "active_strategy_id",
        ):
            if name in cols:
                op.drop_column("owner_rulebooks", name)
