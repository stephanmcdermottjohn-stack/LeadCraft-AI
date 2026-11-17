"""Add users.is_admin + clients_settings.business_type (Phase 3D).

Idempotent: checks information_schema before each ALTER. Safe to re-run.
Usage: python scripts/add_business_type_is_admin.py   (run from backend/)
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
    "where table_schema='public' and table_name='users' and column_name='is_admin'"
)
if cur.fetchone():
    print("users.is_admin already exists - nothing to do.")
else:
    cur.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE")
    conn.commit()
    print("Added users.is_admin (BOOLEAN NOT NULL DEFAULT FALSE).")

cur.execute(
    "select 1 from information_schema.columns "
    "where table_schema='public' and table_name='clients_settings' and column_name='business_type'"
)
if cur.fetchone():
    print("clients_settings.business_type already exists - nothing to do.")
else:
    cur.execute("ALTER TABLE clients_settings ADD COLUMN business_type VARCHAR(50) NOT NULL DEFAULT ''")
    conn.commit()
    print("Added clients_settings.business_type (VARCHAR(50) NOT NULL DEFAULT '').")

cur.close()
conn.close()
