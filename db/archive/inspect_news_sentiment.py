"""
inspect_news_sentiment.py — one-time diagnostic, safe to delete after
running (or archive to db/archive/ per project convention).

Read-only. Checks how many source='news' rows have been scored, and if
so, reports label distribution overall and per-ticker, plus the
relevance-flag rate — since NewsAPI text has no cashtags, expect the
flag to fire almost entirely via the macro-keyword path, not the
cashtag-count path (see relevance_flagger.py).

Independent of the source='stocktwits' exclusivity filter already in
confidence_trajectory — this only looks at the raw scored News rows
themselves, not anything downstream in trajectories or signals.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM sentiment_records WHERE source = 'news'")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM sentiment_records WHERE source = 'news' AND label IS NOT NULL")
    scored = cur.fetchone()[0]
    unscored = total - scored

    print(f"Total source='news' rows: {total}")
    print(f"  Scored (label IS NOT NULL): {scored}")
    print(f"  Unscored (label IS NULL):   {unscored}")

    if scored == 0:
        print("\nNo News rows have been scored yet — finbert_vader_scorer.py hasn't")
        print("run against this data. Run it directly, or run the full")
        print("run_pipeline.py, then re-run this script.")
        conn.close()
        return

    print("\nLabel distribution (source='news', scored rows only):")
    cur.execute(
        """
        SELECT label, COUNT(*) FROM sentiment_records
        WHERE source = 'news' AND label IS NOT NULL
        GROUP BY label
        ORDER BY label
        """
    )
    for label, count in cur.fetchall():
        pct = count / scored * 100
        print(f"  {label:10s} {count:4d}  ({pct:.1f}%)")

    print("\nLabel distribution by ticker:")
    cur.execute(
        """
        SELECT ticker,
               SUM(CASE WHEN label='bullish' THEN 1 ELSE 0 END) AS bull,
               SUM(CASE WHEN label='bearish' THEN 1 ELSE 0 END) AS bear,
               SUM(CASE WHEN label='neutral' THEN 1 ELSE 0 END) AS neut,
               COUNT(*) AS total
        FROM sentiment_records
        WHERE source = 'news' AND label IS NOT NULL
        GROUP BY ticker
        ORDER BY ticker
        """
    )
    print(f"  {'ticker':6s} {'bull':>5s} {'bear':>5s} {'neut':>5s} {'total':>6s}  bull%")
    for ticker, bull, bear, neut, tot in cur.fetchall():
        bull_pct = bull / tot * 100 if tot else 0
        print(f"  {ticker:6s} {bull:5d} {bear:5d} {neut:5d} {tot:6d}  {bull_pct:.1f}%")

    print("\nRelevance-flag rate (source='news'):")
    cur.execute(
        """
        SELECT SUM(CASE WHEN relevance_flag=1 THEN 1 ELSE 0 END), COUNT(*)
        FROM sentiment_records
        WHERE source = 'news' AND relevance_flag IS NOT NULL
        """
    )
    flagged, flag_total = cur.fetchone()
    if flag_total:
        print(f"  {flagged}/{flag_total} flagged low-relevance ({flagged / flag_total * 100:.1f}%)")
        print("  NOTE: news text has no cashtags, so this rate is driven almost")
        print("  entirely by the macro-keyword path, not the cashtag-count path.")
    else:
        print("  No news rows have gone through relevance_flagger.py yet.")

    conn.close()


if __name__ == "__main__":
    run()