"""Add setup_grade and typical_rr to playbook_setups."""

from alembic import op
import sqlalchemy as sa


revision = "20260724_playbook_setup_grade"
down_revision = "20260718_focus_set_at"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("playbook_setups")} if insp.has_table("playbook_setups") else set()
    with op.batch_alter_table("playbook_setups") as batch:
        if "setup_grade" not in cols:
            batch.add_column(sa.Column("setup_grade", sa.String(length=8), nullable=False, server_default=""))
        if "typical_rr" not in cols:
            batch.add_column(sa.Column("typical_rr", sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table("playbook_setups") as batch:
        batch.drop_column("typical_rr")
        batch.drop_column("setup_grade")
