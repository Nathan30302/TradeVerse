"""Daily risk limits plus MAE/MFE and mistake chips on trades.

Revision ID: 20260914_journal_discipline
Revises: 20260730_coach_goals
Create Date: 2026-09-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260914_journal_discipline"
down_revision = "20260730_coach_goals"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("users"):
        cols = {c["name"] for c in insp.get_columns("users")}
        if "daily_loss_limit_r" not in cols:
            op.add_column("users", sa.Column("daily_loss_limit_r", sa.Float(), nullable=True))
        if "daily_max_trades" not in cols:
            op.add_column("users", sa.Column("daily_max_trades", sa.Integer(), nullable=True))

    if insp.has_table("trades"):
        cols = {c["name"] for c in insp.get_columns("trades")}
        if "mae_price" not in cols:
            op.add_column("trades", sa.Column("mae_price", sa.Float(), nullable=True))
        if "mfe_price" not in cols:
            op.add_column("trades", sa.Column("mfe_price", sa.Float(), nullable=True))
        if "mistake_tags" not in cols:
            op.add_column("trades", sa.Column("mistake_tags", sa.String(length=255), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("trades"):
        cols = {c["name"] for c in insp.get_columns("trades")}
        for col in ("mistake_tags", "mfe_price", "mae_price"):
            if col in cols:
                op.drop_column("trades", col)

    if insp.has_table("users"):
        cols = {c["name"] for c in insp.get_columns("users")}
        for col in ("daily_max_trades", "daily_loss_limit_r"):
            if col in cols:
                op.drop_column("users", col)
