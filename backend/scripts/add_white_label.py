"""P3 #2 migration: white-label branding fields on clients_settings.
Idempotent; safe to re-run. Usage: python scripts/add_white_label.py
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

cur.execute("select column_name from information_schema.columns where table_name = 'clients_settings'")
existing = {row[0] for row in cur.fetchall()}

columns = [
    ("brand_name", "VARCHAR(200) NOT NULL DEFAULT ''"),
    ("logo_url", "VARCHAR(500) NOT NULL DEFAULT ''"),
    ("primary_color", "VARCHAR(20) NOT NULL DEFAULT ''"),
    ("support_email", "VARCHAR(320) NOT NULL DEFAULT ''"),
    ("footer_text", "VARCHAR(300) NOT NULL DEFAULT ''"),
    ("hide_platform_brand", "BOOLEAN NOT NULL DEFAULT false"),
]

for name, ddl in columns:
    if name in existing:
        print(f"clients_settings.{name} already exists - nothing to do.")
        continue
    cur.execute(f"ALTER TABLE clients_settings ADD COLUMN {name} {ddl}")
    print(f"Added clients_settings.{name}.")

conn.commit()
cur.close()
conn.close()
