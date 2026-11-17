"""Add lifecycle + attribution columns and lead_stage_history (Phase L, P0).

Idempotent: checks information_schema / to_regclass before each change.
Safe to re-run. Usage: python scripts/add_lifecycle_attribution.py
"""
import os
import sys
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
import psycopg2

load_dotenv()

url = os.environ.get("DATABASE_URL") or ""
if not url.startswith("postgresql"):
    sys.exit("DATABASE_URL must point at Postgres for this migration (got a non-postgres URL).")

parsed = urlparse(url)
conn = psycopg2.connect(
    host=parsed.hostname,
    port=parsed.port or 5432,
    dbname=parsed.path.lstrip("/"),
    user=unquote(parsed.username),
    password=unquote(parsed.password or ""),
    sslmode="require",
    connect_timeout=10,
)
cur = conn.cursor()

VARCHAR_COLUMNS = [
    ("leads", "lifecycle_stage", "VARCHAR(30) NOT NULL DEFAULT 'capture'"),
    ("leads", "grade", "VARCHAR(2) NOT NULL DEFAULT ''"),
    ("leads", "assigned_to", "VARCHAR(200) NOT NULL DEFAULT ''"),
    ("leads", "next_action", "VARCHAR(500) NOT NULL DEFAULT ''"),
    ("leads", "campaign", "VARCHAR(200) NOT NULL DEFAULT ''"),
    ("leads", "utm_source", "VARCHAR(200) NOT NULL DEFAULT ''"),
    ("leads", "utm_medium", "VARCHAR(200) NOT NULL DEFAULT ''"),
    ("leads", "utm_content", "VARCHAR(200) NOT NULL DEFAULT ''"),
    ("leads", "utm_term", "VARCHAR(200) NOT NULL DEFAULT ''"),
    ("leads", "landing_variant", "VARCHAR(50) NOT NULL DEFAULT ''"),
]
for table, column, ddl in VARCHAR_COLUMNS:
    cur.execute(
        "select 1 from information_schema.columns "
        "where table_schema='public' and table_name=%s and column_name=%s",
        (table, column),
    )
    if cur.fetchone():
        print(f"{table}.{column} already exists - skipped.")
    else:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.commit()
        print(f"Added {table}.{column}.")

for table, column in [("leads", "next_action_at")]:
    cur.execute(
        "select 1 from information_schema.columns "
        "where table_schema='public' and table_name=%s and column_name=%s",
        (table, column),
    )
    if cur.fetchone():
        print(f"{table}.{column} already exists - skipped.")
    else:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} TIMESTAMPTZ NULL")
        conn.commit()
        print(f"Added {table}.{column}.")

cur.execute("select to_regclass('public.lead_stage_history')")
if cur.fetchone()[0]:
    print("lead_stage_history already exists - skipped.")
else:
    cur.execute(
        """
        CREATE TABLE lead_stage_history (
            id SERIAL PRIMARY KEY,
            lead_id INTEGER NOT NULL REFERENCES leads(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            from_stage VARCHAR(30) NOT NULL DEFAULT '',
            to_stage VARCHAR(30) NOT NULL,
            note VARCHAR(500) NOT NULL DEFAULT '',
            changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute("CREATE INDEX ix_lead_stage_history_lead_id ON lead_stage_history (lead_id)")
    cur.execute("CREATE INDEX ix_lead_stage_history_user_id ON lead_stage_history (user_id)")
    conn.commit()
    print("Created lead_stage_history (+ indexes).")

# Backfill: already-won leads start at the convert stage.
cur.execute("UPDATE leads SET lifecycle_stage = 'convert' WHERE status = 'converted' AND lifecycle_stage = 'capture'")
if cur.rowcount:
    conn.commit()
    print(f"Backfilled {cur.rowcount} converted leads to the convert stage.")
else:
    print("No lifecycle backfill needed.")

cur.close()
conn.close()
