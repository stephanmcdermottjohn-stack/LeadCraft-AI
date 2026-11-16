"""Read-only check: list public tables in the configured database.

Uses DATABASE_URL from backend/.env (never hardcode credentials).
Usage: python scripts/check_tables.py   (run from backend/)
"""
import os
import sys
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
import psycopg2

load_dotenv()

url = os.environ.get("DATABASE_URL") or ""
if not url.startswith("postgresql"):
    sys.exit("DATABASE_URL must point at Postgres for this check (got a non-postgres URL).")

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
    "select table_name from information_schema.tables "
    "where table_schema = 'public' order by table_name"
)
rows = [r[0] for r in cur.fetchall()]
print("tables in public schema:", rows)
conn.close()
