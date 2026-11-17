"""Add clients_settings.show_property_fields (Phase 3B property module).

Idempotent: checks information_schema before ALTER. Safe to re-run.
Usage: python scripts/add_show_property_fields.py   (run from backend/)
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
    "where table_schema='public' and table_name='clients_settings' and column_name='show_property_fields'"
)
if cur.fetchone():
    print("show_property_fields already exists - nothing to do.")
else:
    cur.execute("ALTER TABLE clients_settings ADD COLUMN show_property_fields BOOLEAN NOT NULL DEFAULT FALSE")
    conn.commit()
    print("Added clients_settings.show_property_fields (BOOLEAN NOT NULL DEFAULT FALSE).")
cur.close()
conn.close()
