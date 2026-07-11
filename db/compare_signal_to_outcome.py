"""
compare_signal_to_outcome.py — Diagnostic: cross-references resolved
earnings_events (signal_direction vs actual_outcome) to check whether
the model's calls track reality.

Read-only. Safe to run anytime; only reports on events where BOTH
signal_direction and actual_outcome are populated (i.e. resolve_signal.py
and resolve_earnings_outcomes.py have both already run for that event).

Bullish/bearish calls get a strict correct/incorrect grade. no_bet
passes are NOT graded correct/incorrect — a pass followed by 'flat' and
a pass followed by a big move are both just reported, since a pass
being "right" (avoided a real gamble) and a pass "missing" a move
that materialized are different questions that shouldn't be
flattened into one pass/fail bucket.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"


def get_resolved_events(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ticker, earnings_date, signal_direction, confidence_score,
               actual_outcome, actual_move_pct
        FROM earnings_events
        WHERE signal_direction IS NOT NULL
          AND actual_outcome IS NOT NULL
          AND actual_outcome != 'pending'
        ORDER BY earnings_date, ticker
        """
    )
    return cur.fetchall()


def grade(signal_direction, actual_outcome):
    if signal_direction == "bullish":
        return "correct" if actual_outcome == "up" else "wrong"
    if signal_direction == "bearish":
        return "correct" if actual_outcome == "down" else "wrong"
    return None  # no_bet — not graded, just reported


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)
    events = get_resolved_events(conn)
    conn.close()

    print(f"{len(events)} events with both a signal and a resolved outcome.\n")

    header = f"{'ticker':6s} {'date':10s} {'signal':8s} {'conf':>6s} {'outcome':7s} {'move%':>7s} {'grade':8s}"
    print(header)
    print("-" * len(header))

    directional_total = 0
    directional_correct = 0

    for ticker, date, signal, conf, outcome, move_pct in events:
        g = grade(signal, outcome)
        conf_str = f"{conf:.3f}" if conf is not None else "  N/A"
        grade_str = g if g else "--"
        print(f"{ticker:6s} {date:10s} {signal:8s} {conf_str:>6s} {outcome:7s} {move_pct:+6.2f}% {grade_str:8s}")

        if g is not None:
            directional_total += 1
            if g == "correct":
                directional_correct += 1

    print()
    if directional_total > 0:
        accuracy = directional_correct / directional_total * 100
        print(f"Directional calls (bullish/bearish only): {directional_correct}/{directional_total} correct ({accuracy:.1f}%)")
    else:
        print("No directional (non-pass) calls among resolved events yet.")

    # Bias check — the all-bullish pattern flagged earlier in the project
    signal_counts = {}
    for _, _, signal, _, _, _ in events:
        signal_counts[signal] = signal_counts.get(signal, 0) + 1
    print(f"\nSignal distribution among resolved events: {signal_counts}")


if __name__ == "__main__":
    run()