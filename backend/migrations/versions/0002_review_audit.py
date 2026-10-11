"""Record who resolved a break and keep an append-only review history."""

import sqlalchemy as sa
from alembic import op

from app.dbtypes import GUID, UTCDateTime

revision = "0002_review_audit"
down_revision = "0001_reconciliation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reconciliation_breaks", sa.Column("resolved_by", sa.String(120)))
    op.create_table(
        "break_events",
        sa.Column("event_id", GUID(), primary_key=True),
        sa.Column("break_id", GUID(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column("break_type", sa.String(30), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("reviewer", sa.String(120), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", UTCDateTime(), nullable=False),
    )
    op.create_index("ix_break_events_break_id", "break_events", ["break_id"])
    op.create_index("ix_break_events_source_created", "break_events", ["source", "created_at"])


def downgrade():
    op.drop_index("ix_break_events_source_created", table_name="break_events")
    op.drop_index("ix_break_events_break_id", table_name="break_events")
    op.drop_table("break_events")
    op.drop_column("reconciliation_breaks", "resolved_by")
