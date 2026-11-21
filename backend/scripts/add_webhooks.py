"""P4 #1 migration: webhook_events + integration routing ids.

Idempotent; safe to re-run. Usage: python scripts/add_webhooks.py
"""
import os
import sys
from urllib.parse import unquote, urlparse

import psycopg2
from dotenv import load_dotenv

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


def has_column(table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return cur.fetchone() is not None


for name in ("meta_page_id", "whatsapp_phone_number_id"):
    if has_column("clients_settings", name):
        print(f"clients_settings.{name} already exists.")
    else:
        cur.execute(
            f"ALTER TABLE clients_settings ADD COLUMN {name} VARCHAR(64) NOT NULL DEFAULT ''"
        )
        print(f"Added clients_settings.{name}.")

cur.execute("select to_regclass('public.webhook_events')")
if cur.fetchone()[0]:
    print("webhook_events already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE webhook_events (
            id SERIAL PRIMARY KEY,
            source VARCHAR(30) NOT NULL,
            event_key VARCHAR(200) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'received',
            user_id INTEGER NULL REFERENCES users(id),
            payload_json TEXT NOT NULL DEFAULT '{}',
            signature_valid BOOLEAN NOT NULL DEFAULT false,
            lead_id INTEGER NULL REFERENCES leads(id),
            error VARCHAR(500) NOT NULL DEFAULT '',
            received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            processed_at TIMESTAMPTZ NULL
        )
        """
    )
    cur.execute("CREATE UNIQUE INDEX ux_webhook_events_event_key ON webhook_events (event_key)")
    print("Created webhook_events.")

    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_webhook_events_event_key ON webhook_events (event_key)")
    print("Created webhook_events.")

cur.execute("CREATE INDEX IF NOT EXISTS ix_webhook_events_source ON webhook_events (source)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_webhook_events_status ON webhook_events (status)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_webhook_events_user_id ON webhook_events (user_id)")
cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_webhook_events_event_key ON webhook_events (event_key)")
print("Webhook indexes ensured.")

conn.commit()
cur.close()
conn.close()
