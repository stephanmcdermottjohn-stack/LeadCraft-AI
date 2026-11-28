"""P7 #2 migration: leads.landing_page_slug (which custom page captured a lead).

Additive and idempotent; safe to re-run. Unlike new tables, a new column is NOT
created by ``create_all`` on an existing database, so this script must run
before the backend that reads the column is deployed.

Usage: python scripts/add_page_lead_source.py   (run from backend/)
"""
import json
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
    host=parsed.hostname, port=parsed.port or 5432, dbname=parsed.path.lstrip("/"),
    user=unquote(parsed.username), password=unquote(parsed.password or ""),
    sslmode="require", connect_timeout=10,
)
cur = conn.cursor()

cur.execute(
    """
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'leads'
      and column_name = 'landing_page_slug'
    """
)
if cur.fetchone():
    print("leads.landing_page_slug already exists - nothing to do.")
else:
    cur.execute("ALTER TABLE leads ADD COLUMN landing_page_slug VARCHAR(60)")
    cur.execute("CREATE INDEX ix_leads_landing_page_slug ON leads (landing_page_slug)")
    print("Added leads.landing_page_slug (+ index).")

# Backfill the few leads captured between P7 #1 and P7 #2. The slug was stored
# in metadata_json only, so read it in Python (never trust the TEXT column to be
# valid JSON). Idempotent: only NULL rows are touched, and slugs are re-checked.
cur.execute(
    "select id, metadata_json from leads "
    "where landing_page_slug is null and metadata_json like '%landing_page%'"
)
updated = 0
for lead_id, raw in cur.fetchall():
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        continue
    slug = parsed.get("landing_page") if isinstance(parsed, dict) else None
    if isinstance(slug, str) and slug.strip():
        cur.execute(
            "update leads set landing_page_slug = %s "
            "where id = %s and landing_page_slug is null",
            (slug.strip()[:60], lead_id),
        )
        updated += 1
if updated:
    print(f"Backfilled landing_page_slug on {updated} existing lead(s).")

conn.commit()
cur.close()
conn.close()
