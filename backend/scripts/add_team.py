"""P3 #1 migration: workspace_members (team members + roles).
Idempotent; safe to re-run. Usage: python scripts/add_team.py
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

cur.execute("select to_regclass('public.workspace_members')")
if cur.fetchone()[0]:
    print("workspace_members already exists - nothing to do.")
else:
    cur.execute(
        """
        CREATE TABLE workspace_members (
            id SERIAL PRIMARY KEY,
            owner_user_id INTEGER NOT NULL REFERENCES users(id),
            member_user_id INTEGER NULL REFERENCES users(id),
            invited_email VARCHAR(320) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'agent',
            status VARCHAR(20) NOT NULL DEFAULT 'invited',
            invite_token VARCHAR(64) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            accepted_at TIMESTAMPTZ NULL,
            CONSTRAINT ux_workspace_members_owner_email UNIQUE (owner_user_id, invited_email)
        )
        """
    )
    print("Created workspace_members (+ owner/email uniqueness).")

cur.execute("CREATE INDEX IF NOT EXISTS ix_workspace_members_owner_user_id ON workspace_members (owner_user_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_workspace_members_member_user_id ON workspace_members (member_user_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_workspace_members_invited_email ON workspace_members (invited_email)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_workspace_members_status ON workspace_members (status)")
cur.execute(
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_workspace_members_invite_token "
    "ON workspace_members (invite_token) WHERE invite_token IS NOT NULL"
)
# One active workspace per person in v1.
cur.execute(
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_workspace_members_active_member "
    "ON workspace_members (member_user_id) WHERE status = 'active' AND member_user_id IS NOT NULL"
)
print("Team indexes ensured (token unique, one active workspace per account).")

conn.commit()
cur.close()
conn.close()
