"""add stripe webhook event ledger

Revision ID: 20260507_add_stripe_webhook_event_ledger
Revises: e41815a5f993
Create Date: 2026-05-07

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260507_add_stripe_webhook_event_ledger"
down_revision = "e41815a5f993"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stripe_webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stripe_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_stripe_webhook_events_stripe_event_id",
        "stripe_webhook_events",
        ["stripe_event_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_stripe_webhook_events_stripe_event_id", table_name="stripe_webhook_events")
    op.drop_table("stripe_webhook_events")

