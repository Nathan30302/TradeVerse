"""add playbook_setups table

Revision ID: 20260508_playbook_setups
Revises: 20260508_ai_coaching_notes
Create Date: 2026-05-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260508_playbook_setups"
down_revision = "20260508_ai_coaching_notes"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("playbook_setups"):
        op.create_table(
            "playbook_setups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(length=140), nullable=False, server_default=""),
            sa.Column("market", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("symbol_hint", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("timeframe", sa.String(length=16), nullable=False, server_default=""),
            sa.Column("entry_criteria", sa.Text(), nullable=False, server_default=""),
            sa.Column("invalidation", sa.Text(), nullable=False, server_default=""),
            sa.Column("management_plan", sa.Text(), nullable=False, server_default=""),
            sa.Column("checklist_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("tags", sa.String(length=180), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    existing = set()
    try:
        existing = {ix.get("name") for ix in insp.get_indexes("playbook_setups")}
    except Exception:
        existing = set()
    if "ix_playbook_setups_user_id" not in existing:
        try:
            op.create_index("ix_playbook_setups_user_id", "playbook_setups", ["user_id"])
        except Exception:
            pass


def downgrade():
    op.drop_index("ix_playbook_setups_user_id", table_name="playbook_setups")
    op.drop_table("playbook_setups")

