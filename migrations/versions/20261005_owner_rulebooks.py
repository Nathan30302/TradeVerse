"""Owner rulebook tables.

Revision ID: 20261005_owner_rulebooks
Revises: 20260914_journal_discipline
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa


revision = "20261005_owner_rulebooks"
down_revision = "20260914_journal_discipline"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("owner_rulebooks"):
        op.create_table(
            "owner_rulebooks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("strategy_name", sa.String(length=160), nullable=False),
            sa.Column("overview", sa.Text(), nullable=True),
            sa.Column("markets", sa.Text(), nullable=True),
            sa.Column("timeframes", sa.String(length=120), nullable=True),
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
            sa.Column("gate_strict", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("account_starting_balance", sa.Float(), nullable=True),
            sa.Column("account_high_water", sa.Float(), nullable=True),
            sa.Column("account_current_balance", sa.Float(), nullable=True),
            sa.Column("risk_base_pct", sa.Float(), nullable=False, server_default="1"),
            sa.Column("risk_min_pct", sa.Float(), nullable=False, server_default="0.25"),
            sa.Column("max_trades_per_day", sa.Integer(), nullable=True),
            sa.Column("max_losses_in_row", sa.Integer(), nullable=True),
            sa.Column("unlocked_date", sa.String(length=10), nullable=True),
            sa.Column("unlocked_note", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_owner_rulebooks_user_id", "owner_rulebooks", ["user_id"], unique=True)

    if not insp.has_table("owner_rule_check_logs"):
        op.create_table(
            "owner_rule_check_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_owner_rule_check_logs_user_id", "owner_rule_check_logs", ["user_id"])
        op.create_index("ix_owner_rule_check_logs_created_at", "owner_rule_check_logs", ["created_at"])


def downgrade():
    op.drop_table("owner_rule_check_logs")
    op.drop_table("owner_rulebooks")
