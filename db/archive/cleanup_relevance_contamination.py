"""
cleanup_relevance_contamination.py — one-time cleanup migration. Run
ONCE from the db/ folder, then move to db/archive/ per project
convention. NOT safe to re-run blindly against the same contamination
twice — see note at the bottom of run().

Context: relevance_flagger.py was flagging rows correctly, but nothing
downstream was actually excluding them — finbert_vader_scorer.py and
build_confidence_trajectory.py both ran before that fix landed, so
every currently-resolved earnings_event was built partly from rows
that should have been screened out as low-relevance (macro noise,
cross-tagged multi-ticker posts).

This script:
  1. Snapshots current earnings_events signal state (before picture).
  2. Nulls scoring fields on sentiment_records rows where
     relevance_flag = 1 AND scored_by = 'finbert_vader_hybrid'.
     StockTwits-tagged rows (scored_by = 'stocktwits_label') are left
     untouched by design — that's the platform's own crowd tag, not
     model output, and the query-level filter in
     build_confidence_trajectory.py already excludes them from
     trajectories regardless of whether the label column is nulled.
  3. Truncates confidence_trajectory and rebuilds it from clean data
     via build_confidence_trajectory.run().
  4. Re-runs resolve_signal.run() to recompute every event's signal.
  5. Prints a before/after table so you can see exactly what changed.

Why nulling instead of just leaving relevance_flag=1 in place and
trusting the query filters: the query filters (already added to
finbert_vader_scorer.py and build_confidence_trajectory.py) stop
FUTURE runs from using this data. They don't undo work already done —
the rows in question still carry a stale label/sentiment_score from
before the flag existed, and nothing re-visits already-labeled rows.
Nulling makes the row correctly read as "not scored" so it's excluded
consistently everywhere, not just wherever a query filter happens to
have been added.
"""
import sys
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"


def snapshot_before(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, ticker, earnings_date, signal_direction, confidence_score, was_pass
        FROM earnings_events
        WHERE signal_direction IS NOT NULL
        ORDER BY ticker, earnings_date
        """
    )
    return {row[0]: row for row in cur.fetchall()}


def null_contaminated_rows(conn):
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE sentiment_records
        SET sentiment_score = NULL,
            finbert_raw = NULL,
            vader_raw = NULL,
            label = NULL,
            idiom_flag = 0,
            disagreement_flag = 0,
            scored_by = NULL
        WHERE relevance_flag = 1
          AND scored_by = 'finbert_vader_hybrid'
        """
    )
    affected = cur.rowcount
    conn.commit()
    return affected


def truncate_trajectory(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM confidence_trajectory")
    existing = cur.fetchone()[0]
    cur.execute("DELETE FROM confidence_trajectory")
    conn.commit()
    return existing


def print_before_after(before, conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, ticker, earnings_date, signal_direction, confidence_score, was_pass
        FROM earnings_events
        WHERE id IN ({})
        ORDER BY ticker, earnings_date
        """.format(",".join(str(k) for k in before.keys())) if before else
        "SELECT id, ticker, earnings_date, signal_direction, confidence_score, was_pass FROM earnings_events WHERE 0"
    )
    after_rows = {row[0]: row for row in cur.fetchall()}

    print("\n" + "=" * 90)
    print("BEFORE / AFTER comparison")
    print("=" * 90)
    header = (f"  {'ticker':6s} {'date':10s} {'old_signal':10s} {'new_signal':10s} "
              f"{'old_conf':>8s} {'new_conf':>8s}  changed?")
    print(header)
    print("  " + "-" * (len(header) - 2))

    flips = []
    for event_id, (eid, ticker, date, old_signal, old_conf, old_pass) in before.items():
        after = after_rows.get(event_id)
        if after is None:
            print(f"  {ticker:6s} {date:10s}  -- event no longer has a resolved signal --")
            continue
        _, _, _, new_signal, new_conf, new_pass = after

        old_conf_str = f"{old_conf:.3f}" if old_conf is not None else "  N/A"
        new_conf_str = f"{new_conf:.3f}" if new_conf is not None else "  N/A"
        changed = "YES" if old_signal != new_signal else ""
        if changed:
            flips.append((ticker, date, old_signal, new_signal))

        print(f"  {ticker:6s} {date:10s} {old_signal:10s} {new_signal:10s} "
              f"{old_conf_str:>8s} {new_conf_str:>8s}  {changed}")

    print()
    if flips:
        print(f"{len(flips)} event(s) flipped signal_direction after cleanup:")
        for ticker, date, old_signal, new_signal in flips:
            print(f"  {ticker:6s} {date:10s}  {old_signal} -> {new_signal}")
    else:
        print("No events flipped signal_direction — confidence scores may have")
        print("shifted, but every directional call held after removing contamination.")
    print("=" * 90 + "\n")


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    print(f"Using database at: {DB_PATH.resolve()}")
    print("This will NULL scoring fields on flagged finbert_vader_hybrid rows,")
    print("TRUNCATE confidence_trajectory, and REBUILD every signal.")
    confirm = input("Type 'yes' to proceed: ").strip().lower()
    if confirm != "yes":
        print("Aborted — no changes made.")
        return

    conn = sqlite3.connect(DB_PATH)

    before = snapshot_before(conn)
    print(f"\nSnapshotted {len(before)} currently-resolved earnings_events.")

    nulled = null_contaminated_rows(conn)
    print(f"Nulled scoring fields on {nulled} contaminated finbert_vader_hybrid rows.")

    deleted = truncate_trajectory(conn)
    print(f"Deleted {deleted} rows from confidence_trajectory.")

    conn.close()  # close before handing off to the imported modules' own connections

    # db/ is this script's own directory when run from there — sibling
    # imports work without sys.path changes as long as it's run in place.
    print("\nRebuilding confidence_trajectory from clean data...")
    import build_confidence_trajectory
    build_confidence_trajectory.run()

    print("\nRe-resolving signals...")
    import resolve_signal
    resolve_signal.run()

    conn = sqlite3.connect(DB_PATH)
    print_before_after(before, conn)
    conn.close()

    print("Done. This script is not safe to re-run against the same")
    print("contamination — the rows it nulled no longer carry relevance_flag=1")
    print("AND scored_by='finbert_vader_hybrid' together, so a second run will")
    print("simply find nothing to null (harmless), but don't rely on that —")
    print("move this file to db/archive/ now that it's served its purpose.")


if __name__ == "__main__":
    run()