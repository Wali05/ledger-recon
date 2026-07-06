"""
Load the internal_ledger.csv into the PostgreSQL 'ledger' table.

Run this after:
  1. docker compose up (PostgreSQL must be healthy)
  2. python generate_data.py (CSV must exist)
  3. The FastAPI app must have run once (to create tables via lifespan)
     OR run: python -c "from app.database import sync_engine, Base; import app.models; Base.metadata.create_all(sync_engine)"

Usage (from within the container or with local Python env):
  python data/load_ledger.py
"""

import csv
import os
from pathlib import Path

import psycopg2

DATA_DIR = Path(__file__).parent
DB_URL = os.getenv(
    "SYNC_DATABASE_URL",
    "postgresql://recon_user:recon_pass@localhost:5432/ledger_recon",
)


def load_ledger():
    path = DATA_DIR / "internal_ledger.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run generate_data.py first.")

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # Truncate first so this script is idempotent (re-runnable)
    cur.execute("TRUNCATE TABLE ledger RESTART IDENTITY CASCADE")

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for row in rows:
        cur.execute(
            """
            INSERT INTO ledger
                (transaction_id, account_id, amount, currency, timestamp, description, status)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (transaction_id) DO NOTHING
            """,
            (
                row["transaction_id"],
                row["account_id"],
                float(row["amount"]),
                row["currency"],
                row["timestamp"],
                row["description"],
                row["status"],
            ),
        )

    conn.commit()
    conn.close()
    print(f"[OK] Loaded {len(rows)} rows into ledger table")


if __name__ == "__main__":
    load_ledger()
