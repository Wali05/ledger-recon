"""Store each break's confidence tier and grouped rows; count retired breaks per job."""

import sqlalchemy as sa
from alembic import op

revision = "0003_match_evidence"
down_revision = "0002_review_audit"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reconciliation_breaks", sa.Column("confidence", sa.String(10)))
    op.add_column("reconciliation_breaks", sa.Column("related_ids", sa.JSON()))
    op.add_column("reconciliation_jobs", sa.Column("breaks_retired", sa.Integer()))


def downgrade():
    op.drop_column("reconciliation_jobs", "breaks_retired")
    op.drop_column("reconciliation_breaks", "related_ids")
    op.drop_column("reconciliation_breaks", "confidence")
