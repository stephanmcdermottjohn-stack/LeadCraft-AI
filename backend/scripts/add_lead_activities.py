"""P0 #6 migration: lead_activities table. Idempotent; safe to re-run.
Usage: python scripts/add_lead_activities.py   (run from backend/)
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
    host=parsed.hostname, port=parsed.port or 5432, dbname=parsed.path.lstrip("/"),
    user=unquote(parsed.username), password=unquote(parsed.password or ""),
    sslmode="require", connect_timeout=10,
)
cur = conn.cursor()
cur.execute("select to_regclass('public.lead_activities')")
if cur.fetchone()[0]:
    print("lead_activities already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE lead_activities (
            id SERIAL PRIMARY KEY,
            lead_id INTEGER NOT NULL REFERENCES leads(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            kind VARCHAR(50) NOT NULL,
            detail VARCHAR(500) NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute("CREATE INDEX ix_lead_activities_lead_id ON lead_activities (lead_id)")
    cur.execute("CREATE INDEX ix_lead_activities_user_id ON lead_activities (user_id)")
    conn.commit()
    print("Created lead_activities (+ indexes).")
cur.close()
conn.close()
