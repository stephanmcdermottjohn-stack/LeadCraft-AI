"""P2 #2 migration: campaign_spends (owner-entered campaign spend).
Idempotent; safe to re-run. Usage: python scripts/add_attribution.py
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

cur.execute("select to_regclass('public.campaign_spends')")
if cur.fetchone()[0]:
    print("campaign_spends already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE campaign_spends (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            campaign VARCHAR(200) NOT NULL,
            spend DOUBLE PRECISION NOT NULL DEFAULT 0,
            currency VARCHAR(10) NOT NULL DEFAULT 'PKR',
            notes VARCHAR(500) NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute("CREATE INDEX ix_campaign_spends_user_id ON campaign_spends (user_id)")
    cur.execute("CREATE INDEX ix_campaign_spends_campaign ON campaign_spends (campaign)")
    cur.execute(
        "CREATE UNIQUE INDEX ux_campaign_spends_user_campaign ON campaign_spends (user_id, campaign)"
    )
    print("Created campaign_spends (+ user/campaign indexes, unique per user+campaign).")

conn.commit()
cur.close()
conn.close()
