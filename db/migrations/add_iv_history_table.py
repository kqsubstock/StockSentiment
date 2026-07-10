"""
add_iv_history_table.py — One-time migration to add the iv_history table.
Safe to re-run.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "pipeline.db"

def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS iv_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            atm_iv REAL,
            spot_price REAL,
            dte INTEGER,
            expiration_used TEXT,
            strike_used REAL,
            source TEXT DEFAULT 'tradier',
            UNIQUE(ticker, date)
        )
    """)

    conn.commit()
    conn.close()
    print("iv_history table created (or already existed).")

if __name__ == "__main__":
    run()