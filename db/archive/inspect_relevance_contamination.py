"""
inspect_relevance_contamination.py — one-time diagnostic, safe to delete
after running (or archive to db/archive/ per project convention).

Read-only. No writes. Answers three questions before any cleanup script
touches data:

  1. How many already-scored/labeled sentiment_records rows are flagged
     relevance_flag=1, broken out by scored_by (finbert_vader_hybrid vs
     stocktwits_label) — since those two cases need different handling
     (model output vs. StockTwits' own crowd tag).

  2. Per earnings_event, per week_relative: how many bullish/bearish
     counts currently baked into confidence_trajectory came from
     flagged rows vs. clean rows — i.e., the size of the swing you'd
     see if those rows were excluded and the trajectory rebuilt.

  3. Which earnings_events had their resolve_signal.py decision
     (signal_direction, confidence_score, was_pass) determined using a
     trajectory that included at least one contaminated week — these
     are the events whose stored signal could change after cleanup.

Run this from the db/ folder (or adjust DB_PATH) with the DB checked
out locally — this needs your actual pipeline.db, not this sandbox.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "pipeline.db"

WEEK_START = -18
WEEK_END = -1


def q1_flagged_and_scored(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT scored_by, label, COUNT(*)
        FROM sentiment_records
        WHERE relevance_flag = 1
          AND label IS NOT NULL
        GROUP BY scored_by, label
        ORDER BY scored_by, label
        """
    )
    rows = cur.fetchall()

    print("=" * 70)
    print("1. Already-scored rows now flagged relevance_flag=1")
    print("=" * 70)
    if not rows:
        print("  None — no contamination found in scored rows.\n")
        return

    total = 0
    by_source = {}
    for scored_by, label, count in rows:
        by_source.setdefault(scored_by, []).append((label, count))
        total += count

    for scored_by, label_counts in by_source.items():
        subtotal = sum(c for _, c in label_counts)
        print(f"\n  scored_by = {scored_by!r}  ({subtotal} rows)")
        for label, count in label_counts:
            print(f"    {label:10s} {count}")

    print(f"\n  TOTAL contaminated scored rows: {total}")
    if any(sb == "stocktwits_label" for sb, _ in [(r[0], r[1]) for r in rows]):
        print("  NOTE: stocktwits_label rows above are StockTwits' own crowd tag,")
        print("        not model output — decide separately whether to null those.")
    print()


def q2_weekly_contamination(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, ticker FROM earnings_events ORDER BY ticker, earnings_date")
    events = cur.fetchall()

    print("=" * 70)
    print("2. Per-event, per-week contamination in evidence counts")
    print("=" * 70)
    print("   (weeks with zero flagged evidence are omitted)\n")

    any_found = False
    affected_event_ids = set()

    for event_id, ticker in events:
        cur.execute(
            """
            SELECT week_relative,
                   SUM(CASE WHEN label='bullish' AND (relevance_flag IS NULL OR relevance_flag=0) THEN 1 ELSE 0 END) AS clean_bull,
                   SUM(CASE WHEN label='bearish' AND (relevance_flag IS NULL OR relevance_flag=0) THEN 1 ELSE 0 END) AS clean_bear,
                   SUM(CASE WHEN label='bullish' AND relevance_flag=1 THEN 1 ELSE 0 END) AS flagged_bull,
                   SUM(CASE WHEN label='bearish' AND relevance_flag=1 THEN 1 ELSE 0 END) AS flagged_bear
            FROM sentiment_records
            WHERE earnings_event_id = ?
              AND week_relative BETWEEN ? AND ?
              AND label IN ('bullish','bearish')
            GROUP BY week_relative
            HAVING flagged_bull > 0 OR flagged_bear > 0
            ORDER BY week_relative
            """,
            (event_id, WEEK_START, WEEK_END),
        )
        rows = cur.fetchall()

        if not rows:
            continue

        any_found = True
        affected_event_ids.add(event_id)
        print(f"  {ticker:6s} event_id={event_id:3d}")
        print(f"    {'week':>5} {'clean_bull':>10} {'clean_bear':>10} {'flag_bull':>9} {'flag_bear':>9}  post-cleanup evidence")
        for week, cb, cbear, fb, fbear in rows:
            post_evidence = cb + cbear
            print(f"    {week:>5} {cb:>10} {cbear:>10} {fb:>9} {fbear:>9}  {post_evidence}")
        print()

    if not any_found:
        print("  No weeks with flagged evidence found — trajectories are clean.\n")

    return affected_event_ids


def q3_affected_resolved_signals(conn, affected_event_ids):
    print("=" * 70)
    print("3. Resolved signals that used a contaminated trajectory")
    print("=" * 70)

    if not affected_event_ids:
        print("  None.\n")
        return

    cur = conn.cursor()
    placeholders = ",".join("?" * len(affected_event_ids))
    cur.execute(
        f"""
        SELECT ticker, earnings_date, id, signal_direction, confidence_score, was_pass
        FROM earnings_events
        WHERE id IN ({placeholders})
          AND signal_direction IS NOT NULL
        ORDER BY ticker, earnings_date
        """,
        tuple(affected_event_ids),
    )
    rows = cur.fetchall()

    if not rows:
        print("  Affected events exist but none have a resolved signal yet.\n")
        return

    print(f"  {len(rows)} resolved event(s) whose current signal may change after cleanup:\n")
    header = f"  {'ticker':6s} {'date':10s} {'event_id':>8s} {'signal':8s} {'conf':>6s} {'was_pass':>8s}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for ticker, date, event_id, signal, conf, was_pass in rows:
        conf_str = f"{conf:.3f}" if conf is not None else "  N/A"
        print(f"  {ticker:6s} {date:10s} {event_id:>8d} {signal:8s} {conf_str:>6s} {was_pass:>8d}")
    print()


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)

    q1_flagged_and_scored(conn)
    affected_event_ids = q2_weekly_contamination(conn)
    q3_affected_resolved_signals(conn, affected_event_ids)

    conn.close()

    print("=" * 70)
    print("This script made no changes. Review the above before running any")
    print("cleanup script that nulls scored fields or rebuilds trajectories.")
    print("=" * 70)


if __name__ == "__main__":
    run()
