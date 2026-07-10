"""
relevance_flagger.py — Flags sentiment_records rows whose raw_text is
likely NOT about this company's earnings specifically (macro noise,
cashtag sweeps, off-topic content sharing the ticker).

Log-only for now: writes cashtag_count, macro_keyword_hit,
earnings_keyword_hit, and the combined relevance_flag. Does not
exclude or alter anything in finbert_vader_scorer.py or
build_confidence_trajectory.py — those stay untouched until we've
seen how many rows get flagged and decided how to act on it.

relevance_flag = 1 if:
    cashtag_count >= CASHTAG_THRESHOLD (3)
    OR (macro_keyword_hit == 1 AND earnings_keyword_hit == 0)

Only processes rows where relevance_flag IS NULL — same idempotent
pattern as finbert_vader_scorer.py. Safe to re-run after fresh scrapes.
"""
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"

CASHTAG_THRESHOLD = 3

MACRO_KEYWORDS = [
    "fed", "fomc", "cpi", "ppi", "rate hike", "rate cut", "interest rates",
    "inflation", "recession", "yields", "treasury", "dxy", "dollar index",
    "jobs report", "nonfarm payrolls", "unemployment rate",
    "tariff", "tariffs", "trade war", "geopolitical",
    "sector rotation", "risk-on", "risk-off", "macro",
]

EARNINGS_KEYWORDS = [
    "earnings", "eps", "guidance", "revenue", "beat", "miss", "beats", "misses",
    "quarter", "quarterly", "q1", "q2", "q3", "q4", "outlook", "forecast",
    "margins", "backlog", "bookings", "subscriber growth", "arr",
    "pre-market", "after hours", "call transcript", "conference call",
]

CASHTAG_PATTERN = re.compile(r"\$[A-Z]{1,5}\b")


def count_cashtags(raw_text):
    return len(CASHTAG_PATTERN.findall(raw_text))


def check_keyword_hit(raw_text, keywords):
    text_lower = raw_text.lower()
    return int(any(re.search(rf"\b{re.escape(kw)}\b", text_lower) for kw in keywords))


def compute_relevance(raw_text):
    cashtag_count = count_cashtags(raw_text)
    macro_hit = check_keyword_hit(raw_text, MACRO_KEYWORDS)
    earnings_hit = check_keyword_hit(raw_text, EARNINGS_KEYWORDS)

    relevance_flag = int(
        cashtag_count >= CASHTAG_THRESHOLD
        or (macro_hit == 1 and earnings_hit == 0)
    )

    return cashtag_count, macro_hit, earnings_hit, relevance_flag


def get_unflagged_records(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, raw_text FROM sentiment_records WHERE relevance_flag IS NULL")
    return cur.fetchall()


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)
    records = get_unflagged_records(conn)
    print(f"Checking relevance for {len(records)} unflagged records...\n")

    cur = conn.cursor()
    flagged_count = 0

    for record_id, raw_text in records:
        cashtag_count, macro_hit, earnings_hit, relevance_flag = compute_relevance(raw_text or "")

        if relevance_flag:
            flagged_count += 1

        cur.execute(
            """UPDATE sentiment_records
               SET cashtag_count = ?, macro_keyword_hit = ?,
                   earnings_keyword_hit = ?, relevance_flag = ?
               WHERE id = ?""",
            (cashtag_count, macro_hit, earnings_hit, relevance_flag, record_id)
        )

    conn.commit()
    print(f"Flagged {flagged_count} of {len(records)} records as low-relevance.")

    cur.execute(
        """
        SELECT ticker, SUM(relevance_flag), COUNT(*)
        FROM sentiment_records
        WHERE relevance_flag IS NOT NULL
        GROUP BY ticker
        ORDER BY ticker
        """
    )
    print("\nFlagged rate by ticker:")
    for ticker, flagged, total in cur.fetchall():
        pct = flagged / total * 100 if total else 0
        print(f"  {ticker:6s} {flagged:4d}/{total:4d}  ({pct:.1f}%)")

    conn.close()


if __name__ == "__main__":
    run()