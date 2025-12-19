
import db

def migrate():
    import sqlite3
    from db import DB_PATH, standardize_courier_name, get_conn

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Ensure user_id column exists
    try:
        c.execute("SELECT user_id FROM tracked LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE tracked ADD COLUMN user_id TEXT")
        conn.commit()

    # 1. Set user_id to 'admin' for legacy rows
    c.execute("UPDATE tracked SET user_id = 'admin' WHERE user_id IS NULL OR user_id = ''")
    user_updated = c.rowcount

    # 2. Normalize courier names (optional, preserves your logic)
    c.execute("SELECT id, courier, last_result FROM tracked")
    rows = c.fetchall()
    courier_updated = 0
    for row in rows:
        item_id, courier, last_result = row
        # Prefer the DB field, fallback to last_result if present
        try:
            import json
            last_result_obj = json.loads(last_result) if last_result else {}
        except Exception:
            last_result_obj = {}
        effective_courier = courier or last_result_obj.get("courier")
        std_courier = standardize_courier_name(effective_courier)
        if std_courier and std_courier != courier:
            c.execute("UPDATE tracked SET courier=? WHERE id=?", (std_courier, item_id))
            courier_updated += 1

    conn.commit()
    conn.close()
    print(f"Migration complete. user_id set for {user_updated} records. {courier_updated} courier records updated.")

if __name__ == "__main__":
    migrate()
