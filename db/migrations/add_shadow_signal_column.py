"""
add_shadow_signal_column.py — One-time migration to add
shadow_signal_direction to earnings_events, supporting
resolve_signal_shadow.py's threshold-geometry comparison. Safe to
re-run — uses the PRAGMA table_info guard pattern already used
elsewhere in this project (see add_relevance_columns.py).

shadow_signal_direction is populated by resolve_signal_shadow.py, not
by resolve_signal.py or anything on the paper-trading path — it is a
monitoring/analysis column only. See resolve_signal_shadow.py's
docstring for the full rationale.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "pipeline.db"


def get_existing_columns(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(earnings_events)")
    return {row[1] for row in cur.fetchall()}


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    existing = get_existing_columns(conn)

    if "shadow_signal_direction" not in existing:
        cur.execute("ALTER TABLE earnings_events ADD COLUMN shadow_signal_direction TEXT")
        conn.commit()
        print("Added column: shadow_signal_direction")
    else:
        print("Column shadow_signal_direction already exists — no changes made.")

    conn.close()


if __name__ == "__main__":
    run()
