"""Create lead_qualifications (roadmap P0 #3, BANT). Idempotent; safe to re-run.
Usage: python scripts/add_lead_qualifications.py   (run from backend/)
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
cur.execute("select to_regclass('public.lead_qualifications')")
if cur.fetchone()[0]:
    print("lead_qualifications already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE lead_qualifications (
            id SERIAL PRIMARY KEY,
            lead_id INTEGER NOT NULL UNIQUE REFERENCES leads(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            budget_value VARCHAR(500) NOT NULL DEFAULT '',
            budget_confidence VARCHAR(20) NOT NULL DEFAULT 'unknown',
            budget_source VARCHAR(20) NOT NULL DEFAULT '',
            authority_value VARCHAR(500) NOT NULL DEFAULT '',
            authority_confidence VARCHAR(20) NOT NULL DEFAULT 'unknown',
            authority_source VARCHAR(20) NOT NULL DEFAULT '',
            need_value VARCHAR(500) NOT NULL DEFAULT '',
            need_confidence VARCHAR(20) NOT NULL DEFAULT 'unknown',
            need_source VARCHAR(20) NOT NULL DEFAULT '',
            timing_value VARCHAR(500) NOT NULL DEFAULT '',
            timing_confidence VARCHAR(20) NOT NULL DEFAULT 'unknown',
            timing_source VARCHAR(20) NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute("CREATE INDEX ix_lead_qualifications_user_id ON lead_qualifications (user_id)")
    conn.commit()
    print("Created lead_qualifications (+ user index, lead unique).")
cur.close()
conn.close()
