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


if __name__ == "__main__":
    init_db()