import sqlite3

def get_db(db_path="riggers.db"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path="riggers.db"):
    conn = get_db(db_path)
    with open("schema.sql", "r") as f:
        conn.executescript(f.read())
    conn.close()
    print("Database initialized.")

if __name__ == "__main__":
    init_db()