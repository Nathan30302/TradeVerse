"""Add coach_goals and coach_challenges tables.

Revision ID: 20260730_coach_goals
Revises: 20260730_coach_memories
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_coach_goals"
down_revision = "20260730_coach_memories"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("coach_goals"):
        op.create_table(
            "coach_goals",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("metric", sa.String(length=40), nullable=False, server_default="custom"),
            sa.Column("target_value", sa.Float(), nullable=True),
            sa.Column("target_text", sa.String(length=400), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("progress_pct", sa.Float(), nullable=False, server_default="0"),
            sa.Column("progress_detail", sa.String(length=400), nullable=False, server_default=""),
            sa.Column("starts_at", sa.DateTime(), nullable=False),
            sa.Column("ends_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        try:
            op.create_index("ix_coach_goals_user_id", "coach_goals", ["user_id"])
        except Exception:
            pass

    if not insp.has_table("coach_challenges"):
        op.create_table(
            "coach_challenges",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("code", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("target_count", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("progress_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("progress_detail", sa.String(length=400), nullable=False, server_default=""),
            sa.Column("review_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("starts_at", sa.DateTime(), nullable=False),
            sa.Column("ends_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        try:
            op.create_index("ix_coach_challenges_user_id", "coach_challenges", ["user_id"])
        except Exception:
            pass


def downgrade():
    for table in ("coach_challenges", "coach_goals"):
        try:
            op.drop_index(f"ix_{table}_user_id", table_name=table)
        except Exception:
            pass
        try:
            op.drop_table(table)
        except Exception:
            pass
