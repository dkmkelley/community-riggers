import sqlite3
import secrets
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'riggers.db')
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def generate_token():
    return secrets.token_urlsafe(32)


def init_db():
    conn = get_db()
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.close()
    print("Database initialized.")


# Applies schema.sql (safe to run on every boot; uses CREATE TABLE IF NOT EXISTS) and adds any
# columns introduced after a database already existed, since CREATE TABLE IF NOT EXISTS alone
# won't alter an existing table.
def ensure_schema():
    conn = get_db()
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(riggers)").fetchall()}
    if "sms_consent" not in columns:
        conn.execute("ALTER TABLE riggers ADD COLUMN sms_consent INTEGER NOT NULL DEFAULT 0")
        conn.commit()

    conn.close()


if __name__ == "__main__":
    init_db()