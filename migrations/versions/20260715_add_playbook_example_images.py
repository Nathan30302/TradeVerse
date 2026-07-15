"""add playbook example_images column

Revision ID: 20260715_playbook_images
Revises: 20260509_user_login_events
Create Date: 2026-07-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260715_playbook_images"
down_revision = "20260509_user_login_events"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("playbook_setups"):
        return
    cols = {c.get("name") for c in insp.get_columns("playbook_setups")}
    if "example_images" not in cols:
        with op.batch_alter_table("playbook_setups") as batch_op:
            batch_op.add_column(
                sa.Column("example_images", sa.Text(), nullable=False, server_default="[]")
            )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("playbook_setups"):
        return
    cols = {c.get("name") for c in insp.get_columns("playbook_setups")}
    if "example_images" in cols:
        with op.batch_alter_table("playbook_setups") as batch_op:
            batch_op.drop_column("example_images")
