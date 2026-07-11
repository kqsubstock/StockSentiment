"""
add_ticker_cursors_table.py — One-time migration to add the
ticker_cursors table. Safe to re-run.

Stores one row per ticker with the highest StockTwits message ID
seen so far (last_since_id). The scraper reads this before each pull
to request only new messages (via the `since` param), and updates it
after a successful pull. NULL last_since_id means this ticker has
never been scraped — the scraper falls back to an unparameterized
call for that case, same as current baseline behavior.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "pipeline.db"

def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ticker_cursors (
            ticker          TEXT PRIMARY KEY REFERENCES companies(ticker),
            last_since_id   TEXT,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()
    print("ticker_cursors table created (or already existed).")

if __name__ == "__main__":
    run()