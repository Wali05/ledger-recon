import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import StatementError
from sqlalchemy.schema import CreateSchema, DropSchema

from app.database import sync_engine
from migrations.schema_v1 import Base as FrozenSchema


def upgrade(engine):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@pytest.fixture
def legacy_engine(tmp_path):
    schema = None
    if sync_engine.dialect.name == "postgresql":
        schema = "recon_migration_test_" + uuid.uuid4().hex
        with sync_engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = create_engine(sync_engine.url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine("sqlite:///" + (tmp_path / "legacy.db").as_posix())
    try:
        yield engine
    finally:
        engine.dispose()
        if schema:
            with sync_engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))


def test_legacy_schema_upgrades_without_losing_resolutions_or_uploads(legacy_engine):
    engine = legacy_engine
    date_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
    id_type = "UUID" if engine.dialect.name == "postgresql" else "CHAR(36)"
    job_id, break_id = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.begin() as connection:
        connection.execute(
            text(f"""CREATE TABLE uploaded_ledger (
            transaction_id VARCHAR PRIMARY KEY, account_id VARCHAR NOT NULL,
            amount NUMERIC(18,4) NOT NULL, currency VARCHAR(3) NOT NULL,
            timestamp {date_type} NOT NULL, description TEXT, status VARCHAR(50) NOT NULL)""")
        )
        connection.execute(
            text(
                "CREATE INDEX ix_uploaded_ledger_transaction_id ON uploaded_ledger(transaction_id)"
            )
        )
        connection.execute(
            text(f"""CREATE TABLE reconciliation_jobs (
            job_id {id_type} PRIMARY KEY, status VARCHAR(20) NOT NULL, source VARCHAR(20) NOT NULL,
            started_at {date_type}, finished_at {date_type}, error_message TEXT,
            transactions_processed NUMERIC, breaks_detected NUMERIC)""")
        )
        connection.execute(
            text(f"""CREATE TABLE reconciliation_breaks (
            break_id {id_type} PRIMARY KEY, transaction_id VARCHAR NOT NULL, break_type VARCHAR(30) NOT NULL,
            internal_amount NUMERIC(18,4), external_amount NUMERIC(18,4), delta_amount NUMERIC(18,4),
            internal_timestamp {date_type}, external_timestamp {date_type}, description TEXT,
            detected_at {date_type} NOT NULL, resolved BOOLEAN NOT NULL, resolved_at {date_type},
            job_id {id_type}, source VARCHAR(20) NOT NULL, ai_explanation TEXT,
            CONSTRAINT uq_break_txn_type_source UNIQUE (transaction_id, break_type, source),
            FOREIGN KEY(job_id) REFERENCES reconciliation_jobs(job_id))""")
        )
        params = {
            "job": job_id,
            "break": break_id,
            "date": "2024-06-01 12:00:00.000000",
            "resolved": True,
        }
        connection.execute(
            text(
                "INSERT INTO uploaded_ledger VALUES ('T1','A',100.1234,'USD',:date,'payment','settled')"
            ),
            params,
        )
        connection.execute(
            text(
                "INSERT INTO reconciliation_jobs (job_id,status,source) VALUES (:job,'complete','uploaded')"
            ),
            params,
        )
        connection.execute(
            text("""INSERT INTO reconciliation_breaks
            (break_id,transaction_id,break_type,internal_amount,external_amount,delta_amount,detected_at,resolved,resolved_at,job_id,source)
            VALUES (:break,'T1','AMOUNT_MISMATCH',100.1234,98.1234,2,:date,:resolved,:date,:job,'uploaded')"""),
            params,
        )
    upgrade(engine)
    upgrade(engine)  # Applying the already-current revision must be a no-op.
    with engine.connect() as connection:
        table = FrozenSchema.metadata.tables["reconciliation_breaks"]
        record = connection.execute(select(table)).mappings().one()
        assert str(record["break_id"]) == break_id
        assert record["resolved"] and record["resolved_at"].tzinfo is not None
        assert record["internal_amount"] == Decimal("100.1234")
        assert record["delta_amount"] == Decimal("2.0000")
        uploaded = FrozenSchema.metadata.tables["uploaded_ledger"]
        assert connection.execute(select(uploaded.c.amount)).scalar_one() == Decimal("100.1234")
        assert not any(name.startswith("legacy_") for name in inspect(connection).get_table_names())


def test_fresh_schema_matches_the_mapped_application_schema(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "fresh.db").as_posix())
    upgrade(engine)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.check(config)
    engine.dispose()


def test_failed_legacy_upgrade_rolls_back_original_data(legacy_engine):
    engine = legacy_engine
    date_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
    with engine.begin() as connection:
        connection.execute(
            text(f"""CREATE TABLE uploaded_ledger (
            transaction_id VARCHAR PRIMARY KEY, account_id VARCHAR NOT NULL,
            amount NUMERIC(20,4) NOT NULL, currency VARCHAR(3) NOT NULL,
            timestamp {date_type} NOT NULL, description TEXT, status VARCHAR(50) NOT NULL)""")
        )
        connection.execute(
            text("""INSERT INTO uploaded_ledger
            VALUES ('TOO-LARGE','A',100000000000000,'USD','2024-06-01','legacy row','settled')""")
        )
    with pytest.raises(StatementError, match="Amount must be finite"):
        upgrade(engine)
    with engine.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("uploaded_ledger")}
        assert "row_id" not in columns
        assert (
            connection.execute(text("SELECT transaction_id FROM uploaded_ledger")).scalar_one()
            == "TOO-LARGE"
        )
        assert "reconciliation_breaks" not in inspect(connection).get_table_names()
