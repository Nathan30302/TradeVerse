"""add broker tables

Revision ID: 20251212_add_broker_tables
Revises: 07e766313e36
Create Date: 2025-12-12 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251212_add_broker_tables'
down_revision = '07e766313e36'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'broker_profiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('broker_id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('broker_id')
    )

    op.create_index(op.f('ix_broker_profiles_broker_id'), 'broker_profiles', ['broker_id'], unique=False)

    op.create_table(
        'user_broker_credentials',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('broker_id', sa.String(length=50), nullable=False),
        sa.Column('encrypted_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    )

    op.create_index(op.f('ix_user_broker_credentials_user_id'), 'user_broker_credentials', ['user_id'], unique=False)

    op.create_table(
        'imported_trade_sources',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('broker_id', sa.String(length=50), nullable=True),
        sa.Column('source_type', sa.String(length=50), nullable=True),
        sa.Column('filename', sa.String(length=255), nullable=True),
        sa.Column('imported_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    )


def downgrade():
    op.drop_table('imported_trade_sources')
    op.drop_index(op.f('ix_user_broker_credentials_user_id'), table_name='user_broker_credentials')
    op.drop_table('user_broker_credentials')
    op.drop_index(op.f('ix_broker_profiles_broker_id'), table_name='broker_profiles')
    op.drop_table('broker_profiles')
