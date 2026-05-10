"""Ensure users.role exists (idempotent guard for partial upgrades).

Revision ID: 20260511_users_role_guard
Revises: 20260510_admin_console
Create Date: 2026-05-10

Some deployments may skip intermediate revisions; the ORM maps ``users.role`` as deferred.
If the column is missing, any code path that touches role would 500. This migration adds
the column only when absent.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260511_users_role_guard"
down_revision = "20260510_admin_console"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("users")}
    if "role" not in cols:
        op.add_column("users", sa.Column("role", sa.String(length=20), nullable=True))
        op.execute(sa.text("UPDATE users SET role = 'user' WHERE role IS NULL"))


def downgrade():
    pass
