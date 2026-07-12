"""
add_source_name_column.py — one-time migration, safe to re-run.

Adds source_name (TEXT) to sentiment_records — the publisher name from
NewsAPI's per-article `source.name` field (e.g. "CNBC", "Biztoc.com",
"GlobeNewswire"), currently discarded on ingest in news_scraper.py.

No DEFAULT — existing rows land as NULL, same as the relevance columns
did. This does NOT backfill existing News rows (see note below); it
only enables capture going forward.

Uses the PRAGMA table_info guard already used elsewhere in this
project — checks the column doesn't already exist before ALTER TABLE.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "pipeline.db"


def get_existing_columns(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(sentiment_records)")
    return {row[1] for row in cur.fetchall()}


def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    existing = get_existing_columns(conn)
    if "source_name" in existing:
        print("source_name already exists — nothing to do.")
    else:
        cur.execute("ALTER TABLE sentiment_records ADD COLUMN source_name TEXT")
        conn.commit()
        print("Added column: source_name")

    conn.close()


if __name__ == "__main__":
    run()