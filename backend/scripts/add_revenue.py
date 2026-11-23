"""P5 #3 migration: manually recorded deal outcomes (revenue & ROI).

Idempotent; safe to re-run. Usage: python scripts/add_revenue.py
"""
import os
import sys
from urllib.parse import unquote, urlparse

import psycopg2
from dotenv import load_dotenv

load_dotenv(".env")

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

cur.execute("select to_regclass('public.deal_outcomes')")
if cur.fetchone()[0]:
    print("deal_outcomes already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE deal_outcomes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            lead_id INTEGER NOT NULL REFERENCES leads(id),
            status VARCHAR(10) NOT NULL DEFAULT 'open',
            amount DOUBLE PRECISION NOT NULL DEFAULT 0,
            currency VARCHAR(10) NOT NULL DEFAULT 'PKR',
            closed_at DATE NULL,
            note VARCHAR(500) NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ux_deal_outcomes_lead UNIQUE (lead_id)
        )
        """
    )
    print("Created deal_outcomes.")

cur.execute("CREATE INDEX IF NOT EXISTS ix_deal_outcomes_user_id ON deal_outcomes (user_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_deal_outcomes_lead_id ON deal_outcomes (lead_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_deal_outcomes_status ON deal_outcomes (status)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_deal_outcomes_closed_at ON deal_outcomes (closed_at)")
print("Deal outcome indexes ensured.")

conn.commit()
cur.close()
conn.close()
