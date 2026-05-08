"""add ai_coaching_notes for premium AI Buddy

Revision ID: 20260508_ai_coaching_notes
Revises: 20260508_weekly_focus
Create Date: 2026-05-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260508_ai_coaching_notes"
down_revision = "20260508_weekly_focus"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("ai_coaching_notes"):
        op.create_table(
            "ai_coaching_notes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("pinned_rule", sa.Text(), nullable=False, server_default=""),
            sa.Column("checklist_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("source", sa.String(length=30), nullable=False, server_default="manual"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    # Ensure index exists (idempotent across partial runs)
    existing = set()
    try:
        existing = {ix.get("name") for ix in insp.get_indexes("ai_coaching_notes")}
    except Exception:
        existing = set()
    if "ix_ai_coaching_notes_user_id" not in existing:
        try:
            op.create_index("ix_ai_coaching_notes_user_id", "ai_coaching_notes", ["user_id"])
        except Exception:
            pass


def downgrade():
    op.drop_index("ix_ai_coaching_notes_user_id", table_name="ai_coaching_notes")
    op.drop_table("ai_coaching_notes")

