"""Add users.ui_font preference for selectable UI typography.

Revision ID: 20260715_user_ui_font
Revises: 20260715_playbook_images
Create Date: 2026-07-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260715_user_ui_font"
down_revision = "20260715_playbook_images"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("users"):
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "ui_font" not in cols:
        op.add_column(
            "users",
            sa.Column("ui_font", sa.String(length=20), nullable=True, server_default="jakarta"),
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("users"):
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "ui_font" in cols:
        op.drop_column("users", "ui_font")
