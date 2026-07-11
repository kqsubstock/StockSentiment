"""
compute_week_relative.py — Links every sentiment_records row to its
nearest upcoming earnings_event per ticker, and computes week_relative
(weeks before that event's pre-earnings cutoff).

Cutoff logic (matches the report_time design in earnings_events):
  - AMC:            cutoff = midnight Eastern the day AFTER earnings_date
                     (the whole earnings day is still "pre-reaction")
  - BMO / unknown:  cutoff = midnight Eastern OF earnings_date
                     (conservative fail-safe — treat unknown as BMO)

A message is linked to the EARLIEST cutoff (for its ticker) that falls
after the message's own timestamp — i.e. the next earnings event it
could plausibly be "pre-" sentiment for. If a ticker has no earnings
event with a cutoff after the message, the row is left unlinked
(week_relative and earnings_event_id both NULL) rather than guessed at.

week_relative is NOT clamped to -12..-1 — a message far outside that
window still gets its real distance stored (e.g. -18). Whether distant
records are useful (e.g. as a leading indicator for a company's *next*
earnings, not just its nearest one) is a modeling decision for later,
not something this script should decide by silently dropping data.

Safe to re-run: recomputes every row from scratch each time, so
updating an unconfirmed earnings_date later (e.g. PLTR, ABNB) and
re-running this script will correct any records that were linked
against the old estimate.
"""
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from earnings_cutoff import compute_cutoff_utc

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"
EASTERN = ZoneInfo("America/New_York")


def load_earnings_cutoffs(conn):
    """Returns {ticker: [(cutoff_utc_datetime, earnings_event_id), ...]} sorted ascending."""
    cur = conn.cursor()
    cur.execute("SELECT id, ticker, earnings_date, report_time FROM earnings_events")

    by_ticker = {}
    for event_id, ticker, earnings_date_str, report_time in cur.fetchall():
        cutoff_utc = compute_cutoff_utc(earnings_date_str, report_time)
        by_ticker.setdefault(ticker, []).append((cutoff_utc, event_id))

    for ticker in by_ticker:
        by_ticker[ticker].sort(key=lambda pair: pair[0])

    return by_ticker


def parse_message_timestamp(ts_str):
    """StockTwits/Reddit timestamps come in as ISO 8601 UTC, e.g. '2026-07-09T02:11:51Z'."""
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


def find_next_cutoff(cutoffs, message_time):
    """Returns (cutoff_utc, event_id) for the earliest cutoff after message_time, or (None, None)."""
    for cutoff_utc, event_id in cutoffs:
        if cutoff_utc > message_time:
            return cutoff_utc, event_id
    return None, None


def compute_week_relative():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)
    cutoffs_by_ticker = load_earnings_cutoffs(conn)

    cur = conn.cursor()
    cur.execute("SELECT id, ticker, timestamp FROM sentiment_records")
    records = cur.fetchall()

    updates = []
    linked_count = 0
    unlinked_count = 0

    for record_id, ticker, timestamp_str in records:
        cutoffs = cutoffs_by_ticker.get(ticker, [])
        message_time = parse_message_timestamp(timestamp_str)

        cutoff_utc, event_id = find_next_cutoff(cutoffs, message_time)

        if cutoff_utc is None:
            updates.append((None, None, record_id))
            unlinked_count += 1
            continue

        days_before = (cutoff_utc - message_time).total_seconds() / 86400
        weeks_before = math.ceil(days_before / 7)
        week_relative = -weeks_before

        updates.append((week_relative, event_id, record_id))
        linked_count += 1

    cur.executemany(
        "UPDATE sentiment_records SET week_relative = ?, earnings_event_id = ? WHERE id = ?",
        updates,
    )
    conn.commit()

    print(f"Processed {len(records)} sentiment_records rows.")
    print(f"  Linked:   {linked_count}")
    print(f"  Unlinked: {unlinked_count} (no future earnings event found for that ticker)")

    # Quick sanity check — distribution of week_relative values
    cur.execute(
        """
        SELECT week_relative, COUNT(*)
        FROM sentiment_records
        WHERE week_relative IS NOT NULL
        GROUP BY week_relative
        ORDER BY week_relative
        """
    )
    print("\nweek_relative distribution:")
    for week, count in cur.fetchall():
        print(f"  {week:4d}: {count}")

    conn.close()


def run():
    compute_week_relative()


if __name__ == "__main__":
    run()