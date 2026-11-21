"""P5 #1 migration: booking settings + appointments.

Idempotent; safe to re-run. Usage: python scripts/add_booking.py
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


def has_column(table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return cur.fetchone() is not None


columns = [
    ("booking_enabled", "BOOLEAN NOT NULL DEFAULT false"),
    ("booking_slot_minutes", "INTEGER NOT NULL DEFAULT 30"),
    ("booking_start", "VARCHAR(5) NOT NULL DEFAULT '10:00'"),
    ("booking_end", "VARCHAR(5) NOT NULL DEFAULT '18:00'"),
    ("booking_days_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("booking_timezone", "VARCHAR(64) NOT NULL DEFAULT 'Asia/Karachi'"),
    ("booking_services_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("booking_lead_minutes", "INTEGER NOT NULL DEFAULT 60"),
    ("booking_note", "VARCHAR(300) NOT NULL DEFAULT ''"),
]
for name, ddl in columns:
    if has_column("clients_settings", name):
        print(f"clients_settings.{name} already exists.")
    else:
        cur.execute(f"ALTER TABLE clients_settings ADD COLUMN {name} {ddl}")
        print(f"Added clients_settings.{name}.")

cur.execute("select to_regclass('public.appointments')")
if cur.fetchone()[0]:
    print("appointments already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE appointments (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            lead_id INTEGER NOT NULL REFERENCES leads(id),
            starts_at TIMESTAMPTZ NOT NULL,
            ends_at TIMESTAMPTZ NOT NULL,
            service VARCHAR(100) NOT NULL DEFAULT '',
            source VARCHAR(30) NOT NULL DEFAULT 'public_booking',
            status VARCHAR(20) NOT NULL DEFAULT 'booked',
            owner_notes VARCHAR(1000) NOT NULL DEFAULT '',
            reminded_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    print("Created appointments.")

cur.execute("CREATE INDEX IF NOT EXISTS ix_appointments_user_id ON appointments (user_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_appointments_lead_id ON appointments (lead_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_appointments_starts_at ON appointments (starts_at)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_appointments_status ON appointments (status)")
print("Appointment indexes ensured.")

conn.commit()
cur.close()
conn.close()
