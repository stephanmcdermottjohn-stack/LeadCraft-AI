"""Set/rotate a login password from the terminal (security pass).

Usage (from the backend folder):
    python scripts/set_password.py --email owner@example.com
    python scripts/set_password.py --email owner@example.com --password "new-secret"

Why this exists: the API has no password-change endpoint yet, and after a
credential leak the fastest safe fix is to rewrite the PBKDF2 hash directly.
This uses the exact same hashing function as registration (390k iterations,
16-byte salt), so login keeps working untouched.

The password is never printed, logged or passed on a command line unless you
explicitly use --password (interactive prompt is recommended).
"""
import argparse
import getpass
import os
import sys
from urllib.parse import unquote, urlparse

import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.auth_service import hash_password  # noqa: E402

MIN_LEN = 8
MAX_LEN = 128


def read_password() -> str:
    first = getpass.getpass("New password: ")
    if not (MIN_LEN <= len(first) <= MAX_LEN):
        sys.exit(f"Password must be {MIN_LEN}-{MAX_LEN} characters.")
    if first != getpass.getpass("Repeat new password: "):
        sys.exit("Passwords did not match.")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(description="Set a login password in the workspace database.")
    parser.add_argument("--email", required=True, help="Login email of the account to update.")
    parser.add_argument(
        "--password",
        default="",
        help="New password. Omit to be prompted (recommended - avoids shell history).",
    )
    args = parser.parse_args()

    email = args.email.strip().lower()
    password = args.password or read_password()
    if not (MIN_LEN <= len(password) <= MAX_LEN):
        sys.exit(f"Password must be {MIN_LEN}-{MAX_LEN} characters.")

    load_dotenv(".env")
    url = os.environ.get("DATABASE_URL") or ""
    if not url.startswith("postgresql"):
        sys.exit("DATABASE_URL must point at Postgres for this operation.")

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
    try:
        cur = conn.cursor()
        cur.execute("select id from users where lower(email) = %s", (email,))
        rows = cur.fetchall()
        if not rows:
            sys.exit(f"No account found for {email}.")
        cur.execute(
            "update users set password_hash = %s where lower(email) = %s",
            (hash_password(password), email),
        )
        if cur.rowcount != 1:
            sys.exit(f"Expected 1 row, updated {cur.rowcount}. Nothing committed.")
        conn.commit()
        print(f"Password updated for {email}. Existing bearer tokens stay valid until they expire.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
