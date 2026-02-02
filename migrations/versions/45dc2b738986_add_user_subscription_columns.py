"""add user subscription columns

Revision ID: 45dc2b738986
Revises: 20251212_add_instrument_aliases
Create Date: 2025-12-11 20:40:03.226970

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '45dc2b738986'
down_revision = '20251212_add_instrument_aliases'
branch_labels = None
depends_on = None


def upgrade():
    # No-op migration - subscription columns and foreign key already exist in DB
    # This migration serves as a checkpoint to record schema state
    pass


def downgrade():
    # No-op downgrade - subscription columns should persist
    pass