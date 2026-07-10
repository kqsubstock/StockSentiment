"""
inspect_relevance_calls.py — one-time diagnostic, safe to delete after
running.

Read-only. Pulls a sample of CRWD rows flagged as low-relevance, and a
sample of MSFT rows NOT flagged, so the actual calls can be eyeballed
against raw_text. Exists to sanity-check two anomalies in the first
relevance_flagger.py run: CRWD's flag rate was higher than expected,
MSFT's was lower than expected.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"
SAMPLE_SIZE = 15


def print_sample(conn, ticker, want_flagged, label):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT raw_text, cashtag_count, macro_keyword_hit, earnings_keyword_hit
        FROM sentiment_records
        WHERE ticker = ? AND relevance_flag = ?
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (ticker, 1 if want_flagged else 0, SAMPLE_SIZE),
    )
    rows = cur.fetchall()

    print(f"\n{'='*70}")
    print(f"{label} — {len(rows)} rows")
    print(f"{'='*70}")
    for raw_text, cashtags, macro_hit, earnings_hit in rows:
        print(f"\n[cashtags={cashtags} macro={macro_hit} earnings={earnings_hit}]")
        print(f"  {raw_text[:300]}")


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)

    print_sample(conn, "CRWD", want_flagged=True,
                 label="CRWD — FLAGGED as low-relevance")
    print_sample(conn, "MSFT", want_flagged=False,
                 label="MSFT — NOT flagged (let through)")

    conn.close()


if __name__ == "__main__":
    run()
    