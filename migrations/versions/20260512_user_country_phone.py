"""Add optional country_code and phone_number to users.

Revision ID: 20260512_user_country_phone
Revises: 20260511_users_role_guard
Create Date: 2026-05-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260512_user_country_phone"
down_revision = "20260511_users_role_guard"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("users"):
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "country_code" not in cols:
        op.add_column("users", sa.Column("country_code", sa.String(length=2), nullable=True))
    if "phone_number" not in cols:
        op.add_column("users", sa.Column("phone_number", sa.String(length=32), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("users"):
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "phone_number" in cols:
        op.drop_column("users", "phone_number")
    if "country_code" in cols:
        op.drop_column("users", "country_code")
