"""Security pass migration: DB-backed auth throttle counters.

Idempotent; safe to re-run. Usage: python scripts/add_auth_limits.py
"""
import os
import sys
from urllib.parse import unquote, urlparse

import psycopg2
from dotenv import load_dotenv

load_dotenv(".env")

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

cur.execute("select to_regclass('public.auth_throttles')")
if cur.fetchone()[0]:
    print("auth_throttles already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE auth_throttles (
            key_hash VARCHAR(64) PRIMARY KEY,
            failures INTEGER NOT NULL DEFAULT 0,
            window_start TIMESTAMPTZ NOT NULL DEFAULT now(),
            locked_until TIMESTAMPTZ NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    print("Created auth_throttles.")

cur.execute("CREATE INDEX IF NOT EXISTS ix_auth_throttles_updated_at ON auth_throttles (updated_at)")
print("Auth throttle indexes ensured.")

conn.commit()
cur.close()
conn.close()
