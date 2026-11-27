"""P7 #1 migration: landing_pages (custom block-built pages). Idempotent; safe
to re-run. Usage: python scripts/add_landing_pages.py   (run from backend/)

``Base.metadata.create_all`` also creates this table on boot, so this script is
for environments that migrate explicitly and for parity with the other
migrations.
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

cur.execute("select to_regclass('public.landing_pages')")
if cur.fetchone()[0]:
    print("landing_pages already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE landing_pages (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            slug VARCHAR(60) NOT NULL UNIQUE,
            title VARCHAR(200) NOT NULL DEFAULT '',
            blocks_json TEXT NOT NULL DEFAULT '[]',
            is_published BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute("CREATE INDEX ix_landing_pages_user_id ON landing_pages (user_id)")
    print("Created landing_pages (+ user index, unique slug).")

conn.commit()
cur.close()
conn.close()
