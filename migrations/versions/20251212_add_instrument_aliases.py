"""add instrument aliases table

Revision ID: 20251212_add_instrument_aliases
Revises: 20251212_add_broker_tables
Create Date: 2025-12-12 00:00:00.000001
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251212_add_instrument_aliases'
down_revision = '20251212_add_broker_tables'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'instrument_aliases',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('instrument_id', sa.Integer(), sa.ForeignKey('instruments.id'), nullable=False),
        sa.Column('alias', sa.String(length=100), nullable=False),
    )
    op.create_index(op.f('ix_instrument_aliases_alias'), 'instrument_aliases', ['alias'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_instrument_aliases_alias'), table_name='instrument_aliases')
    op.drop_table('instrument_aliases')
