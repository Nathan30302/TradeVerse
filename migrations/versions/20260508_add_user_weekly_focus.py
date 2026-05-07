"""add users.weekly_focus_rule for onboarding / AI capture

Revision ID: 20260508_weekly_focus
Revises: 20260507_add_user_role_and_pro_plus
Create Date: 2026-05-08

"""

from alembic import op
import sqlalchemy as sa


revision = "20260508_weekly_focus"
down_revision = "20260507_add_user_role_and_pro_plus"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("weekly_focus_rule", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("weekly_focus_rule")
