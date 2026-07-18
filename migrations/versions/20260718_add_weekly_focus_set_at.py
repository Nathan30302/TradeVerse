"""Add users.weekly_focus_set_at for focus compliance window.

Revision ID: 20260718_focus_set_at
Revises: 20260715_user_ui_font
Create Date: 2026-07-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260718_focus_set_at"
down_revision = "20260715_user_ui_font"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("users"):
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "weekly_focus_set_at" not in cols:
        op.add_column(
            "users",
            sa.Column("weekly_focus_set_at", sa.DateTime(), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("users"):
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "weekly_focus_set_at" in cols:
        op.drop_column("users", "weekly_focus_set_at")
