"""Add clients_settings.landing_slug (Phase 3 landing pages).

Idempotent: checks information_schema before ALTER. Safe to re-run.
Usage: python scripts/add_landing_slug.py   (run from backend/)
"""
import os
import sys
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
import psycopg2

load_dotenv()

url = os.environ.get("DATABASE_URL") or ""
if not url.startswith("postgresql"):
    sys.exit("DATABASE_URL must point at Postgres for this migration (got a non-postgres URL).")

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
cur.execute(
    "select 1 from information_schema.columns "
    "where table_schema='public' and table_name='clients_settings' and column_name='landing_slug'"
)
if cur.fetchone():
    print("landing_slug already exists — nothing to do.")
else:
    cur.execute("ALTER TABLE clients_settings ADD COLUMN landing_slug VARCHAR(100) UNIQUE")
    conn.commit()
    print("Added clients_settings.landing_slug (VARCHAR(100) UNIQUE).")
cur.close()
conn.close()
