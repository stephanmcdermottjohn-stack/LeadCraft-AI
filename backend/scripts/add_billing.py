"""P3 #3 migration: billing_entries (manual ledger, no gateway).
Idempotent; safe to re-run. Usage: python scripts/add_billing.py
"""
import os
import sys
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
import psycopg2

load_dotenv()

url = os.environ.get("DATABASE_URL") or ""
if not url.startswith("postgresql"):
    sys.exit("DATABASE_URL must point at Postgres for this migration.")

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

cur.execute("select to_regclass('public.billing_entries')")
if cur.fetchone()[0]:
    print("billing_entries already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE billing_entries (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            amount DOUBLE PRECISION NOT NULL,
            currency VARCHAR(10) NOT NULL DEFAULT 'PKR',
            period_start DATE NULL,
            period_end DATE NULL,
            paid_until DATE NULL,
            note VARCHAR(500) NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    print("Created billing_entries.")

cur.execute("CREATE INDEX IF NOT EXISTS ix_billing_entries_user_id ON billing_entries (user_id)")
print("Billing indexes ensured.")

conn.commit()
cur.close()
conn.close()
