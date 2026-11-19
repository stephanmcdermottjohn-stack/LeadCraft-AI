"""P2 #1 migration: review_requests + lead referral columns.
Idempotent; safe to re-run. Usage: python scripts/add_reviews_referrals.py
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

cur.execute("select to_regclass('public.review_requests')")
if cur.fetchone()[0]:
    print("review_requests already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE review_requests (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            lead_id INTEGER NOT NULL REFERENCES leads(id),
            channel VARCHAR(30) NOT NULL DEFAULT 'whatsapp',
            status VARCHAR(20) NOT NULL DEFAULT 'requested',
            note VARCHAR(500) NOT NULL DEFAULT '',
            requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ NULL
        )
        """
    )
    cur.execute("CREATE INDEX ix_review_requests_user_id ON review_requests (user_id)")
    cur.execute("CREATE INDEX ix_review_requests_lead_id ON review_requests (lead_id)")
    print("Created review_requests (+ user/lead indexes).")

cur.execute(
    "select column_name from information_schema.columns where table_name = 'leads'"
)
existing = {row[0] for row in cur.fetchall()}

if "referral_code" in existing:
    print("leads.referral_code already exists - nothing to do.")
else:
    cur.execute("ALTER TABLE leads ADD COLUMN referral_code VARCHAR(24) NULL")
    print("Added leads.referral_code.")

if "referred_by_lead_id" in existing:
    print("leads.referred_by_lead_id already exists - nothing to do.")
else:
    cur.execute("ALTER TABLE leads ADD COLUMN referred_by_lead_id INTEGER NULL")
    cur.execute(
        """
        ALTER TABLE leads
        ADD CONSTRAINT fk_leads_referred_by_lead_id
        FOREIGN KEY (referred_by_lead_id) REFERENCES leads(id)
        """
    )
    print("Added leads.referred_by_lead_id (+ self FK).")

cur.execute("CREATE INDEX IF NOT EXISTS ix_leads_referral_code ON leads (referral_code)")
cur.execute(
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_leads_user_referral_code "
    "ON leads (user_id, referral_code) WHERE referral_code IS NOT NULL"
)
cur.execute(
    "CREATE INDEX IF NOT EXISTS ix_leads_referred_by_lead_id ON leads (referred_by_lead_id)"
)
print("Referral indexes ensured.")

conn.commit()
cur.close()
conn.close()
