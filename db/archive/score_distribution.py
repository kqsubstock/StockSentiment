"""
score_distribution.py — one-time diagnostic, safe to delete after running.

Read-only. Buckets sentiment_score across all finbert_vader_hybrid rows
to check whether the ~65% neutral rate is a real distribution shape or
an artifact of the +/-0.3 threshold placement. Also breaks the same
data down by ticker, since a skew could be concentrated in a few names
rather than spread evenly across the roster.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"
BULLISH_THRESHOLD = 0.3
BEARISH_THRESHOLD = -0.3


def get_scores(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ticker, sentiment_score, label
        FROM sentiment_records
        WHERE scored_by = 'finbert_vader_hybrid' AND sentiment_score IS NOT NULL
        """
    )
    return cur.fetchall()


def bucket_index(score):
    """Buckets -1.0..1.0 into 10 bins of width 0.2. Clamp edge case of score == 1.0."""
    idx = int((score + 1.0) / 0.2)
    return min(idx, 9)


def print_histogram(scores):
    buckets = [0] * 10
    for score in scores:
        buckets[bucket_index(score)] += 1

    max_count = max(buckets) if buckets else 1
    print("\nsentiment_score distribution (bucket width 0.2):\n")
    for i in range(10):
        low = -1.0 + i * 0.2
        high = low + 0.2
        bar_len = int((buckets[i] / max_count) * 50) if max_count else 0
        bar = "#" * bar_len
        print(f"  [{low:+.1f}, {high:+.1f})  {buckets[i]:4d}  {bar}")


def print_threshold_breakdown(scores):
    bullish = sum(1 for s in scores if s > BULLISH_THRESHOLD)
    bearish = sum(1 for s in scores if s < BEARISH_THRESHOLD)
    neutral = len(scores) - bullish - bearish

    total = len(scores)
    print(f"\nThreshold breakdown (+/-{BULLISH_THRESHOLD}), n={total}:")
    print(f"  Bullish (> {BULLISH_THRESHOLD:+.1f}):  {bullish:4d}  ({bullish/total*100:.1f}%)")
    print(f"  Bearish (< {BEARISH_THRESHOLD:+.1f}):  {bearish:4d}  ({bearish/total*100:.1f}%)")
    print(f"  Neutral (between):    {neutral:4d}  ({neutral/total*100:.1f}%)")


def print_label_breakdown(rows):
    from collections import Counter
    label_counts = Counter(label for _, _, label in rows)
    total = len(rows)
    print(f"\nLabel column breakdown (as stored), n={total}:")
    for label, count in label_counts.most_common():
        print(f"  {label:10s} {count:4d}  ({count/total*100:.1f}%)")


def print_by_ticker(rows):
    from collections import defaultdict
    by_ticker = defaultdict(list)
    for ticker, score, _ in rows:
        by_ticker[ticker].append(score)

    print(f"\nNeutral rate by ticker:")
    for ticker in sorted(by_ticker):
        scores = by_ticker[ticker]
        neutral = sum(1 for s in scores if BEARISH_THRESHOLD <= s <= BULLISH_THRESHOLD)
        total = len(scores)
        print(f"  {ticker:6s} n={total:4d}  neutral={neutral:4d}  ({neutral/total*100:.1f}%)")


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)
    rows = get_scores(conn)
    conn.close()

    if not rows:
        print("No finbert_vader_hybrid-scored rows found.")
        return

    scores = [score for _, score, _ in rows]

    print_histogram(scores)
    print_threshold_breakdown(scores)
    print_label_breakdown(rows)
    print_by_ticker(rows)


if __name__ == "__main__":
    run()