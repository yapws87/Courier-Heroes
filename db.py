
import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH: Path = Path(__file__).resolve().parent / "tracked.db"

def standardize_courier_name(name: str | None) -> str | None:
    if not name:
        return None
    name = name.strip().lower()
    mapping = {
        'cj logistics': 'CJ Logistics',
        'cj대한통운': 'CJ Logistics',
        'cj': 'CJ Logistics',
        'cvsnet': 'CVSNet (GS25)',
        'gs25': 'CVSNet (GS25)',
        'cu post': 'CUpost',
        'cupost': 'CUpost',
        'cu': 'CUpost',
        'hanjin': 'Hanjin',
        '한진택배': 'Hanjin',
        'korea post': 'Korea Post',
        '우체국': 'Korea Post',
        'lotte': 'Lotte',
        '롯데택배': 'Lotte',
        '롯데글로벌로지스': 'Lotte',
        'logen': 'Logen',
        '로젠택배': 'Logen',
        'ems': 'EMS',
        '7-11': '7-Eleven',
        '7-Eleven': '7-Eleven',
    }
    return mapping.get(name, name.title())


def get_conn() -> sqlite3.Connection:
    conn: sqlite3.Connection = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn: sqlite3.Connection = get_conn()
    c: sqlite3.Cursor = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tracked (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            tracking TEXT NOT NULL,
            courier TEXT,
            label TEXT,
            last_result TEXT,
            last_checked TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    # If the column 'user_id', 'courier', or 'label' was added after table creation in older DBs,
    # ensure they exist (SQLite ignores ADD COLUMN if exists, so we guard)
    for col in ["user_id", "courier", "label"]:
        try:
            c.execute(f"SELECT {col} FROM tracked LIMIT 1")
        except sqlite3.OperationalError:
            c.execute(f"ALTER TABLE tracked ADD COLUMN {col} TEXT")
    conn.commit()
    conn.close()

def list_tracked(user_id):
    conn: sqlite3.Connection = get_conn()
    c: sqlite3.Cursor = conn.cursor()
    c.execute("SELECT id, tracking, courier, label, last_result, last_checked, created_at FROM tracked WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    out = []
    for r in rows:
        courier = r[2]
        label = r[3]
        lr_raw = r[4]
        try:
            lr: sqlite3.Any | None = json.loads(lr_raw) if lr_raw else None
        except Exception:
            lr = None
        out.append({
            "id": r[0],
            "tracking": r[1],
            "courier": courier,
            "label": label,
            "last_result": lr,
            "last_checked": r[5],
            "created_at": r[6],
        })
    return out

def add_tracked(user_id, tracking, courier=None, label=None) -> int | None:
    conn: sqlite3.Connection = get_conn()
    c: sqlite3.Cursor = conn.cursor()
    now: str = datetime.utcnow().isoformat()
    std_courier = standardize_courier_name(courier)
    try:
        c.execute(
            "INSERT INTO tracked (user_id, tracking, courier, label, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, tracking, std_courier, label, now)
        )
        conn.commit()
        rowid: int | None = c.lastrowid
    except sqlite3.IntegrityError:
        rowid = None
    conn.close()
    return rowid

def update_tracked_courier(item_id, courier) -> bool:
    conn: sqlite3.Connection = get_conn()
    c: sqlite3.Cursor = conn.cursor()
    c.execute("UPDATE tracked SET courier=? WHERE id=?", (courier, item_id))
    conn.commit()
    updated: int = c.rowcount
    conn.close()
    return updated > 0


def update_tracked_label(user_id, item_id, label) -> bool:
    conn: sqlite3.Connection = get_conn()
    c: sqlite3.Cursor = conn.cursor()
    c.execute("UPDATE tracked SET label=? WHERE id=? AND user_id=?", (label, item_id, user_id))
    conn.commit()
    updated: int = c.rowcount
    conn.close()
    return updated > 0

def remove_tracked(user_id, item_id) -> bool:
    conn: sqlite3.Connection = get_conn()
    c: sqlite3.Cursor = conn.cursor()
    c.execute("DELETE FROM tracked WHERE id=? AND user_id=?", (item_id, user_id))
    conn.commit()
    deleted: int = c.rowcount
    conn.close()
    return deleted > 0

def update_tracked_result(item_id, result) -> None:
    conn: sqlite3.Connection = get_conn()
    c: sqlite3.Cursor = conn.cursor()
    now: str = datetime.utcnow().isoformat()
    c.execute("UPDATE tracked SET last_result=?, last_checked=? WHERE id=?", (json.dumps(result, ensure_ascii=False), now, item_id))
    conn.commit()
    conn.close()
