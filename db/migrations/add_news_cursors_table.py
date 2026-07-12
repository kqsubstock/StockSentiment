"""
add_news_cursors_table.py — One-time migration to add the
news_cursors table. Safe to re-run.

Mirrors ticker_cursors (used by the StockTwits scraper) but stores a
timestamp instead of a message ID, since NewsAPI's /v2/everything
endpoint pages by publish date, not by an incrementing numeric ID.

Kept as a separate table rather than extending ticker_cursors: that
table's PRIMARY KEY is ticker alone, so reusing it for a second source
on the same ticker would collide with the StockTwits cursor for that
ticker.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "pipeline.db"


def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS news_cursors (
            ticker              TEXT PRIMARY KEY REFERENCES companies(ticker),
            last_fetched_at     TEXT,
            updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()
    print("news_cursors table created (or already existed).")


if __name__ == "__main__":
    run()
