import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "tracked.db"

def print_tracked():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT id, user_id, tracking, courier, label, created_at FROM tracked ORDER BY id")
    rows = c.fetchall()
    print(f"{'ID':<4} {'USER_ID':<15} {'TRACKING':<20} {'COURIER':<15} {'LABEL':<15} {'CREATED_AT'}")
    print('-'*80)
    for row in rows:
        print(f"{row[0]:<4} {row[1]:<15} {row[2]:<20} {row[3] or '':<15} {row[4] or '':<15} {row[5]}")
    conn.close()

if __name__ == "__main__":
    print_tracked()
