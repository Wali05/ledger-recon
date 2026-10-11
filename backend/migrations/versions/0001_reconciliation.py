"""Version the schema and preserve data from pre-Alembic checkouts.

The schema snapshot is frozen in schema_v1.py, not imported from app.models.
SQLite legacy NUMERIC amounts are normalized to their declared four places;
precision already lost by old floating point writes cannot be reconstructed.
"""

import hashlib
import json

import sqlalchemy as sa
from alembic import op

from migrations.schema_v1 import Base

revision = "0001_reconciliation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if (
        connection.dialect.name == "sqlite"
        and not connection.connection.dbapi_connection.in_transaction
    ):
        # SQLite's legacy driver does not begin transactions for DDL itself.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    inspector = sa.inspect(connection)
    names = [
        "ledger",
        "uploaded_ledger",
        "uploaded_statement",
        "reconciliation_jobs",
        "reconciliation_breaks",
    ]
    legacy = {}
    for name in names:
        if inspector.has_table(name):
            table = sa.Table(name, sa.MetaData(), autoload_with=connection)
            legacy[name] = [dict(row) for row in connection.execute(sa.select(table)).mappings()]
    # Stage readable rows before rebuilding. Dropping in dependency order also
    # releases PostgreSQL index/sequence names that a table rename would retain.
    for name in reversed(names):
        if name in legacy:
            op.drop_table(name)
    Base.metadata.create_all(connection)
    for name in names:
        rows = legacy.get(name, [])
        if not rows:
            continue
        table = Base.metadata.tables[name]
        for row in rows:
            if name == "reconciliation_jobs" and row["status"] in ("pending", "running"):
                row.update(
                    status="failed",
                    error_message="Interrupted by schema upgrade; rerun reconciliation",
                )
            if name == "reconciliation_breaks":
                side, occurrence = "pair", 0
                if row["break_type"] == "MISSING_EXTERNAL":
                    side = "internal"
                elif row["break_type"] == "MISSING_INTERNAL":
                    side = "external"
                if row["break_type"] == "DUPLICATE":
                    side = "internal" if row.get("internal_amount") is not None else "external"
                    occurrence = 1
                key = [row["transaction_id"], row["break_type"], side, occurrence]
                row.update(
                    break_key=hashlib.sha256(json.dumps(key).encode()).hexdigest(),
                    evidence_side=side,
                    occurrence=occurrence,
                    external_transaction_id=row["transaction_id"]
                    if row.get("external_amount") is not None
                    else None,
                )
            connection.execute(
                table.insert().values(
                    **{key: value for key, value in row.items() if key in table.c}
                )
            )
    state = Base.metadata.tables["dataset_state"]
    connection.execute(
        state.insert(),
        [
            {"source": "synthetic", "ledger_rows": 0, "statement_rows": 0},
            {
                "source": "uploaded",
                "ledger_rows": len(legacy.get("uploaded_ledger", [])),
                "statement_rows": len(legacy.get("uploaded_statement", [])),
            },
        ],
    )


def downgrade():
    raise RuntimeError("This migration is forward-only. Restore a database backup to revert it.")
