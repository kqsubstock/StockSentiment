"""
add_relevance_columns.py — one-time migration, safe to re-run.

Adds four columns to sentiment_records supporting the relevance filter:
  - cashtag_count        INTEGER  — how many tickers are mentioned in the post
  - macro_keyword_hit    INTEGER  — 1 if raw_text contains macro-only language
  - earnings_keyword_hit INTEGER  — 1 if raw_text contains earnings-adjacent language
  - relevance_flag       INTEGER  — 1 if the row is likely NOT about this company's
                                    earnings specifically (combination of the above)

No DEFAULT on any column — existing rows land as NULL on all four,
so relevance_flagger.py can use "relevance_flag IS NULL" to find
unprocessed rows, same pattern as finbert_vader_scorer.py using
"label IS NULL".

Uses the PRAGMA table_info guard already used elsewhere in this
project — checks which columns exist before ALTER TABLE, so this can
be re-run safely without erroring on "duplicate column."
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"

NEW_COLUMNS = [
    ("cashtag_count", "INTEGER"),
    ("macro_keyword_hit", "INTEGER"),
    ("earnings_keyword_hit", "INTEGER"),
    ("relevance_flag", "INTEGER"),
]


def get_existing_columns(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(sentiment_records)")
    return {row[1] for row in cur.fetchall()}  # row[1] is column name


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    existing = get_existing_columns(conn)
    added = []

    for column_name, column_def in NEW_COLUMNS:
        if column_name not in existing:
            cur.execute(f"ALTER TABLE sentiment_records ADD COLUMN {column_name} {column_def}")
            added.append(column_name)

    conn.commit()
    print(f"Added columns: {', '.join(added)}" if added else "No columns added — all already present.")
    conn.close()


if __name__ == "__main__":
    run()