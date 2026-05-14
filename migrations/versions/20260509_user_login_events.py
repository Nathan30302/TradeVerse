"""Add user_login_events for login history.

Revision ID: 20260509_user_login_events
Revises: 20260512_user_country_phone
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "20260509_user_login_events"
down_revision = "20260512_user_country_phone"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("user_login_events"):
        return
    op.create_table(
        "user_login_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
    )
    op.create_index("ix_user_login_events_user_id", "user_login_events", ["user_id"])
    op.create_index("ix_user_login_events_occurred_at", "user_login_events", ["occurred_at"])


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("user_login_events"):
        return
    op.drop_index("ix_user_login_events_occurred_at", table_name="user_login_events")
    op.drop_index("ix_user_login_events_user_id", table_name="user_login_events")
    op.drop_table("user_login_events")
