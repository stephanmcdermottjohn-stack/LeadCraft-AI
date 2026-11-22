"""P5 #2 migration: workspace audit log.

Idempotent; safe to re-run. Usage: python scripts/add_ops.py
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

cur.execute("select to_regclass('public.audit_logs')")
if cur.fetchone()[0]:
    print("audit_logs already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE audit_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            actor_user_id INTEGER NULL REFERENCES users(id),
            actor_email VARCHAR(320) NOT NULL DEFAULT '',
            action VARCHAR(60) NOT NULL DEFAULT '',
            target_type VARCHAR(40) NOT NULL DEFAULT '',
            target_id VARCHAR(60) NOT NULL DEFAULT '',
            detail_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    print("Created audit_logs.")

cur.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs (action)")
cur.execute(
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_user_created ON audit_logs (user_id, created_at DESC)"
)
print("Audit log indexes ensured.")

conn.commit()
cur.close()
conn.close()
