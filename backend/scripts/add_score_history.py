"""P0 #5 migration: lead_score_history table + clients_settings.scoring_weights_json.
Idempotent; safe to re-run. Usage: python scripts/add_score_history.py  (from backend/)
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

cur.execute("select to_regclass('public.lead_score_history')")
if cur.fetchone()[0]:
    print("lead_score_history already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE lead_score_history (
            id SERIAL PRIMARY KEY,
            lead_id INTEGER NOT NULL REFERENCES leads(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            score INTEGER NOT NULL,
            grade VARCHAR(2) NOT NULL DEFAULT '',
            reason_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute("CREATE INDEX ix_lead_score_history_lead_id ON lead_score_history (lead_id)")
    cur.execute("CREATE INDEX ix_lead_score_history_user_id ON lead_score_history (user_id)")
    print("Created lead_score_history (+ indexes).")

cur.execute(
    "select column_name from information_schema.columns "
    "where table_name='clients_settings' and column_name='scoring_weights_json'"
)
col = cur.fetchone()
if col and col[0]:
    print("scoring_weights_json column already exists.")
else:
    cur.execute("ALTER TABLE clients_settings ADD COLUMN scoring_weights_json TEXT NOT NULL DEFAULT ''")
    print("Added clients_settings.scoring_weights_json.")

conn.commit()
cur.close()
conn.close()
