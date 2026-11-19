"""P1 #4 migration: analytics_events (first-party, cookie-free website events).
Idempotent; safe to re-run. Usage: python scripts/add_analytics.py  (from backend/)
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

cur.execute("select to_regclass('public.analytics_events')")
if cur.fetchone()[0]:
    print("analytics_events already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE analytics_events (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            slug VARCHAR(100) NOT NULL,
            session_id VARCHAR(64) NOT NULL,
            event VARCHAR(30) NOT NULL,
            path VARCHAR(200) NOT NULL DEFAULT '',
            referrer VARCHAR(200) NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute("CREATE INDEX ix_analytics_events_user_id ON analytics_events (user_id)")
    cur.execute("CREATE INDEX ix_analytics_events_slug ON analytics_events (slug)")
    cur.execute("CREATE INDEX ix_analytics_events_session_id ON analytics_events (session_id)")
    print("Created analytics_events (+ user/slug/session indexes).")

conn.commit()
cur.close()
conn.close()
