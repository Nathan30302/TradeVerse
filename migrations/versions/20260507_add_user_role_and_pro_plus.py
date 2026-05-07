"""add user role and pro_plus tier

Revision ID: 20260507_add_user_role_and_pro_plus
Revises: 20260507_add_stripe_webhook_event_ledger
Create Date: 2026-05-07

"""

from alembic import op
import sqlalchemy as sa


revision = "20260507_add_user_role_and_pro_plus"
down_revision = "20260507_add_stripe_webhook_event_ledger"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("role", sa.String(length=20), nullable=True))

    # Backfill role to 'user'
    op.execute("UPDATE users SET role='user' WHERE role IS NULL")


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("role")

