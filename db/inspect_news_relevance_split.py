"""
inspect_news_relevance_split.py — one-time diagnostic, safe to delete
after running (or archive to db/archive/ per project convention).

Read-only. For source='news' rows, breaks bullish/bearish counts down
per ticker into clean (relevance_flag=0 or NULL) vs. flagged
(relevance_flag=1), so a real directional tilt can be told apart from
one that's partly driven by macro-noise articles that happen to
mention the ticker in passing.

Run relevance_flagger.py before this — it reports "not yet flagged"
and stops if no source='news' rows have gone through it.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) FROM sentiment_records WHERE source = 'news' AND relevance_flag IS NOT NULL"
    )
    flagged_total = cur.fetchone()[0]

    if flagged_total == 0:
        print("No source='news' rows have relevance_flag set yet.")
        print("Run relevance_flagger.py first, then re-run this script.")
        conn.close()
        return

    cur.execute(
        """
        SELECT ticker,
               SUM(CASE WHEN label='bullish' AND (relevance_flag IS NULL OR relevance_flag=0) THEN 1 ELSE 0 END) AS clean_bull,
               SUM(CASE WHEN label='bearish' AND (relevance_flag IS NULL OR relevance_flag=0) THEN 1 ELSE 0 END) AS clean_bear,
               SUM(CASE WHEN label='bullish' AND relevance_flag=1 THEN 1 ELSE 0 END) AS flag_bull,
               SUM(CASE WHEN label='bearish' AND relevance_flag=1 THEN 1 ELSE 0 END) AS flag_bear
        FROM sentiment_records
        WHERE source = 'news' AND label IN ('bullish', 'bearish')
        GROUP BY ticker
        ORDER BY ticker
        """
    )
    rows = cur.fetchall()
    conn.close()

    print("News bull/bear split — clean vs. relevance-flagged, per ticker\n")
    header = (f"  {'ticker':6s} {'clean_bull':>10s} {'clean_bear':>10s} "
              f"{'flag_bull':>9s} {'flag_bear':>9s}  clean_bull%")
    print(header)
    print("  " + "-" * (len(header) - 2))

    for ticker, cb, cbear, fb, fbear in rows:
        clean_total = cb + cbear
        clean_bull_pct = (cb / clean_total * 100) if clean_total else 0.0
        print(f"  {ticker:6s} {cb:10d} {cbear:10d} {fb:9d} {fbear:9d}  {clean_bull_pct:.1f}%")

    print("\nRead clean_bull% as the ticker's bullish rate AFTER excluding flagged")
    print("rows — compare it to the unfiltered bull% from inspect_news_sentiment.py")
    print("to see how much of any tilt was riding on macro-noise articles.")


if __name__ == "__main__":
    run()