"""Create icp_profiles (Phase P0 #2). Idempotent; safe to re-run.
Usage: python scripts/add_icp_profiles.py   (run from backend/)
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
cur.execute("select to_regclass('public.icp_profiles')")
if cur.fetchone()[0]:
    print("icp_profiles already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE icp_profiles (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name VARCHAR(100) NOT NULL,
            industry VARCHAR(100) NOT NULL DEFAULT '',
            company_size VARCHAR(50) NOT NULL DEFAULT '',
            location VARCHAR(200) NOT NULL DEFAULT '',
            budget_min INTEGER NULL,
            budget_max INTEGER NULL,
            business_type VARCHAR(50) NOT NULL DEFAULT '',
            needs VARCHAR(1000) NOT NULL DEFAULT '',
            preferred_services VARCHAR(1000) NOT NULL DEFAULT '',
            decision_authority VARCHAR(200) NOT NULL DEFAULT '',
            buying_timeline VARCHAR(200) NOT NULL DEFAULT '',
            criteria_json TEXT NOT NULL DEFAULT '[]',
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute("CREATE INDEX ix_icp_profiles_user_id ON icp_profiles (user_id)")
    conn.commit()
    print("Created icp_profiles (+ user index).")
cur.close()
conn.close()
