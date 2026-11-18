"""P1 #2 migration: nurture_campaigns, nurture_enrollments, nurture_suppressions.
Idempotent; safe to re-run. Usage: python scripts/add_nurture.py  (from backend/)
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

cur.execute("select to_regclass('public.nurture_campaigns')")
if cur.fetchone()[0]:
    print("nurture_campaigns already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE nurture_campaigns (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name VARCHAR(100) NOT NULL,
            steps_json TEXT NOT NULL DEFAULT '[]',
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute("CREATE INDEX ix_nurture_campaigns_user_id ON nurture_campaigns (user_id)")
    print("Created nurture_campaigns (+ user index).")

cur.execute("select to_regclass('public.nurture_enrollments')")
if cur.fetchone()[0]:
    print("nurture_enrollments already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE nurture_enrollments (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            campaign_id INTEGER NOT NULL REFERENCES nurture_campaigns(id),
            lead_id INTEGER NOT NULL REFERENCES leads(id),
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            steps_total INTEGER NOT NULL DEFAULT 0,
            current_step INTEGER NOT NULL DEFAULT 0,
            enrolled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            next_step_at TIMESTAMPTZ NULL,
            completed_at TIMESTAMPTZ NULL
        )
        """
    )
    for col in ("user_id", "campaign_id", "lead_id"):
        cur.execute(f"CREATE INDEX ix_nurture_enrollments_{col} ON nurture_enrollments ({col})")
    cur.execute(
        "CREATE UNIQUE INDEX ux_nurture_enrollments_campaign_lead ON nurture_enrollments (campaign_id, lead_id)"
    )
    print("Created nurture_enrollments (+ indexes, unique campaign+lead).")

cur.execute("select to_regclass('public.nurture_suppressions')")
if cur.fetchone()[0]:
    print("nurture_suppressions already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE nurture_suppressions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            value VARCHAR(320) NOT NULL,
            reason VARCHAR(200) NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute("CREATE INDEX ix_nurture_suppressions_user_id ON nurture_suppressions (user_id)")
    cur.execute("CREATE INDEX ix_nurture_suppressions_value ON nurture_suppressions (value)")
    print("Created nurture_suppressions (+ indexes).")

conn.commit()
cur.close()
conn.close()
