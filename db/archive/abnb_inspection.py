"""
inspect_abnb_backfill_depth.py — one-time diagnostic, safe to delete
after running (or archive to db/archive/ per project convention).

Read-only. Investigates why ABNB's confidence_trajectory shows 10 weeks
of evidence (event_id=20) while every other ticker tops out around 2-3,
and why ABNB event_id=19 (May 7 earnings, already past) has evidence at
all despite compute_week_relative.py only linking a message to a FUTURE
cutoff relative to its own timestamp.

Three checks, in order:

  1. Per earnings_event: earliest/latest timestamp among its linked
     sentiment_records, plus the full week_relative range actually
     present. Confirms whether ABNB event 19 truly has pre-May-7
     messages, and how far back.

  2. Per ticker: how many sentiment_records came in on the EARLIEST
     date_collected day present for that ticker (i.e. the first
     scraper run), vs. total records overall. A first-run backfill
     that reached unusually far back in time would show up as an
     outsized single-day count for ABNB relative to its total.

  3. Per ticker: the set of week_relative values actually present,
     and which weeks in [min, max] are MISSING. A real gap pattern
     here (present at -12 and -3 but missing -8 through -5, say)
     points at the known cursor-advancement bug rather than backfill
     depth — vs. ABNB's case, which should look like a genuinely
     deep, mostly-contiguous backfill if that's really what happened.

Makes no writes. Safe to run anytime.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"


def check1_event_time_ranges(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ee.ticker, ee.id, ee.earnings_date, ee.report_time,
               MIN(sr.timestamp), MAX(sr.timestamp),
               MIN(sr.week_relative), MAX(sr.week_relative),
               COUNT(*)
        FROM earnings_events ee
        JOIN sentiment_records sr ON sr.earnings_event_id = ee.id
        WHERE sr.source = 'stocktwits'
          AND sr.label IN ('bullish', 'bearish')
          AND (sr.relevance_flag IS NULL OR sr.relevance_flag = 0)
        GROUP BY ee.id
        ORDER BY ee.ticker, ee.earnings_date
        """
    )
    rows = cur.fetchall()

    print("=" * 100)
    print("1. Per-event time range of linked bullish/bearish StockTwits evidence")
    print("=" * 100)
    header = (f"  {'ticker':6s} {'event_id':>8s} {'earn_date':10s} {'rpt':7s} "
              f"{'earliest_ts':20s} {'latest_ts':20s} {'wk_min':>6s} {'wk_max':>6s} {'n':>5s}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for ticker, eid, edate, rtime, min_ts, max_ts, wk_min, wk_max, n in rows:
        flag = "  <- past earnings_date, has evidence" if edate < "2026-07-12" else ""
        print(f"  {ticker:6s} {eid:>8d} {edate:10s} {rtime:7s} "
              f"{min_ts:20s} {max_ts:20s} {wk_min:>6d} {wk_max:>6d} {n:>5d}{flag}")
    print()


def check2_first_run_volume(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ticker, date(date_collected) AS collected_date, COUNT(*)
        FROM sentiment_records
        WHERE source = 'stocktwits'
        GROUP BY ticker, collected_date
        ORDER BY ticker, collected_date
        """
    )
    rows = cur.fetchall()

    by_ticker = {}
    for ticker, day, count in rows:
        by_ticker.setdefault(ticker, []).append((day, count))

    print("=" * 100)
    print("2. First scraper-run volume vs. total, per ticker")
    print("=" * 100)
    header = f"  {'ticker':6s} {'first_day':12s} {'first_day_n':>12s} {'total_n':>9s} {'first_day_%':>12s}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for ticker in sorted(by_ticker):
        days = by_ticker[ticker]
        first_day, first_n = days[0]
        total_n = sum(c for _, c in days)
        pct = first_n / total_n * 100 if total_n else 0
        flag = "  <- unusually deep first pull?" if pct > 50 else ""
        print(f"  {ticker:6s} {first_day:12s} {first_n:>12d} {total_n:>9d} {pct:>11.1f}%{flag}")
    print()


def check3_week_gaps(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ticker, week_relative, COUNT(*)
        FROM sentiment_records
        WHERE source = 'stocktwits'
          AND label IN ('bullish', 'bearish')
          AND (relevance_flag IS NULL OR relevance_flag = 0)
          AND week_relative IS NOT NULL
        GROUP BY ticker, week_relative
        ORDER BY ticker, week_relative
        """
    )
    rows = cur.fetchall()

    by_ticker = {}
    for ticker, week, count in rows:
        by_ticker.setdefault(ticker, {})[week] = count

    print("=" * 100)
    print("3. week_relative coverage and gaps per ticker (evidence-qualifying rows only)")
    print("=" * 100)
    for ticker in sorted(by_ticker):
        weeks_present = by_ticker[ticker]
        wk_min, wk_max = min(weeks_present), max(weeks_present)
        missing = [w for w in range(wk_min, wk_max + 1) if w not in weeks_present]
        present_str = ", ".join(f"{w}:{weeks_present[w]}" for w in sorted(weeks_present))
        print(f"\n  {ticker:6s} range=[{wk_min}, {wk_max}]  present weeks: {present_str}")
        if missing:
            print(f"         MISSING weeks in range: {missing}")
        else:
            print(f"         no gaps — fully contiguous")
    print()


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)

    check1_event_time_ranges(conn)
    check2_first_run_volume(conn)
    check3_week_gaps(conn)

    conn.close()

    print("=" * 100)
    print("This script made no changes. Review output above:")
    print("  - Check 1 confirms/refutes whether ABNB event 19 has genuine pre-cutoff evidence")
    print("  - Check 2 tests the 'ABNB is low-volume so backfill reached further back' theory")
    print("  - Check 3 tests whether OTHER tickers have real gaps (cursor bug) rather than")
    print("    ABNB simply having deeper history")
    print("=" * 100)


if __name__ == "__main__":
    run()