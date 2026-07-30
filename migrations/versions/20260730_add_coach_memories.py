"""Add coach_memories table for AI Coach long-term memory.

Revision ID: 20260730_coach_memories
Revises: 20260724_playbook_setup_grade
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_coach_memories"
down_revision = "20260724_playbook_setup_grade"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("coach_memories"):
        op.create_table(
            "coach_memories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("kind", sa.String(length=40), nullable=False, server_default="note"),
            sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("meta_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        try:
            op.create_index("ix_coach_memories_user_id", "coach_memories", ["user_id"])
        except Exception:
            pass


def downgrade():
    try:
        op.drop_index("ix_coach_memories_user_id", table_name="coach_memories")
    except Exception:
        pass
    op.drop_table("coach_memories")
