"""P1 #1 migration: landing_variants + landing_events. Idempotent; safe to
re-run. Usage: python scripts/add_landing_ab.py   (run from backend/)
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

cur.execute("select to_regclass('public.landing_variants')")
if cur.fetchone()[0]:
    print("landing_variants already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE landing_variants (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            label VARCHAR(50) NOT NULL,
            headline VARCHAR(300) NOT NULL DEFAULT '',
            subtext TEXT NOT NULL DEFAULT '',
            cta_label VARCHAR(100) NOT NULL DEFAULT '',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute("CREATE INDEX ix_landing_variants_user_id ON landing_variants (user_id)")
    print("Created landing_variants (+ user index).")

cur.execute("select to_regclass('public.landing_events')")
if cur.fetchone()[0]:
    print("landing_events already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE landing_events (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            slug VARCHAR(100) NOT NULL,
            variant VARCHAR(50) NOT NULL DEFAULT 'control',
            event VARCHAR(50) NOT NULL DEFAULT 'impression',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute("CREATE INDEX ix_landing_events_user_id ON landing_events (user_id)")
    cur.execute("CREATE INDEX ix_landing_events_slug ON landing_events (slug)")
    print("Created landing_events (+ indexes).")

conn.commit()
cur.close()
conn.close()
