"""add broker profile system

Revision ID: 20251215_add_broker_system
Revises: 20251212_add_imported_source_fk_to_trades
Create Date: 2025-12-15 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '20251215_add_broker_system'
down_revision = '20251212_add_imported_source_fk_to_trades'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'broker_profiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('broker_id', sa.String(length=50), nullable=False, unique=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('symbol_patterns', sa.JSON()),
        sa.Column('symbol_mappings', sa.JSON()),
        sa.Column('lot_size_rule', sa.JSON()),
        sa.Column('pip_rules', sa.JSON()),
        sa.Column('tick_rules', sa.JSON()),
        sa.Column('account_currency_options', sa.JSON()),
        sa.Column('api_supported', sa.Boolean(), default=False),
        sa.Column('api_type', sa.String(length=50)),
        sa.Column('api_auth_method', sa.String(length=50)),
        sa.Column('api_base_url', sa.String(length=255)),
        sa.Column('api_docs_url', sa.String(length=255)),
        sa.Column('import_formats', sa.JSON()),
        sa.Column('csv_format', sa.JSON()),
        sa.Column('notes', sa.Text()),
        sa.Column('website', sa.String(length=255)),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now())
    )
    op.create_index(op.f('ix_broker_profiles_broker_id'), 'broker_profiles', ['broker_id'], unique=True)
    
    op.create_table(
        'user_broker_credentials',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('broker_profile_id', sa.Integer(), sa.ForeignKey('broker_profiles.id'), nullable=False),
        sa.Column('nickname', sa.String(length=100)),
        sa.Column('account_id', sa.String(length=100)),
        sa.Column('account_currency', sa.String(length=10), default='USD'),
        sa.Column('encrypted_api_key', sa.Text()),
        sa.Column('encrypted_api_secret', sa.Text()),
        sa.Column('encrypted_access_token', sa.Text()),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_demo', sa.Boolean(), default=False),
        sa.Column('last_sync_at', sa.DateTime()),
        sa.Column('last_sync_status', sa.String(length=50)),
        sa.Column('last_sync_error', sa.Text()),
        sa.Column('consent_given_at', sa.DateTime()),
        sa.Column('consent_ip', sa.String(length=50)),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now())
    )
    op.create_index(op.f('ix_user_broker_credentials_user_id'), 'user_broker_credentials', ['user_id'])


def downgrade():
    op.drop_index(op.f('ix_user_broker_credentials_user_id'), table_name='user_broker_credentials')
    op.drop_table('user_broker_credentials')
    op.drop_index(op.f('ix_broker_profiles_broker_id'), table_name='broker_profiles')
    op.drop_table('broker_profiles')
