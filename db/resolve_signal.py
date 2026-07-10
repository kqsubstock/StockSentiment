"""
resolve_signal.py — Resolves each earnings_event's confidence_trajectory
into a final signal_direction + confidence_score, locked in at week -2
(per design decision: matches options-chain pull timing, and avoids
using weeks -1/-0 which would leak future evidence into a decision
that must be made before earnings).

For each earnings_event, finds the latest confidence_trajectory row
with week_relative <= DECISION_WEEK — never later, to prevent lookahead.
If no row exists that early at all, the event is logged as no_bet with
zero evidence rather than guessed at.

Decision logic, evidence floor checked BEFORE the threshold:
  - evidence_count < MIN_EVIDENCE     -> no_bet (insufficient evidence)
  - posterior_mean >= BULLISH_THRESHOLD -> bullish
  - posterior_mean <= BEARISH_THRESHOLD -> bearish
  - otherwise                          -> no_bet (dead zone)

confidence_score is stored even on a pass, so pass decisions remain
reviewable in hindsight (Decision Rule 3).

Safe to re-run: recomputes every event from scratch each time.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"

DECISION_WEEK = -2
MIN_EVIDENCE = 10
BULLISH_THRESHOLD = 0.65
BEARISH_THRESHOLD = 0.35


def get_all_earnings_events(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, ticker FROM earnings_events ORDER BY ticker, earnings_date")
    return cur.fetchall()


def get_signal_as_of_week(conn, earnings_event_id, decision_week):
    """Latest confidence_trajectory row with week_relative <= decision_week,
    or None if no evidence exists that early."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT week_relative, cumulative_bullish, cumulative_bearish, posterior_mean
        FROM confidence_trajectory
        WHERE earnings_event_id = ? AND week_relative <= ?
        ORDER BY week_relative DESC
        LIMIT 1
        """,
        (earnings_event_id, decision_week),
    )
    return cur.fetchone()


def resolve_event(conn, earnings_event_id):
    row = get_signal_as_of_week(conn, earnings_event_id, DECISION_WEEK)

    if row is None:
        return {
            "signal_direction": "no_bet", "confidence_score": None, "was_pass": 1,
            "evidence_count": 0, "reason": f"no evidence by week {DECISION_WEEK}",
        }

    week_used, cum_bullish, cum_bearish, posterior_mean = row
    evidence_count = cum_bullish + cum_bearish

    if evidence_count < MIN_EVIDENCE:
        return {
            "signal_direction": "no_bet", "confidence_score": posterior_mean, "was_pass": 1,
            "evidence_count": evidence_count,
            "reason": f"insufficient evidence ({evidence_count} < {MIN_EVIDENCE}), as of week {week_used}",
        }

    if posterior_mean >= BULLISH_THRESHOLD:
        signal_direction, was_pass = "bullish", 0
    elif posterior_mean <= BEARISH_THRESHOLD:
        signal_direction, was_pass = "bearish", 0
    else:
        signal_direction, was_pass = "no_bet", 1

    return {
        "signal_direction": signal_direction, "confidence_score": posterior_mean, "was_pass": was_pass,
        "evidence_count": evidence_count, "reason": f"{signal_direction}, as of week {week_used}",
    }


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    events = get_all_earnings_events(conn)
    print(f"Resolving signals for {len(events)} earnings events...\n")

    for earnings_event_id, ticker in events:
        r = resolve_event(conn, earnings_event_id)

        cur.execute(
            """UPDATE earnings_events
               SET signal_direction = ?, confidence_score = ?, was_pass = ?
               WHERE id = ?""",
            (r["signal_direction"], r["confidence_score"], r["was_pass"], earnings_event_id),
        )

        conf_str = f"{r['confidence_score']:.3f}" if r["confidence_score"] is not None else "  N/A"
        print(f"  {ticker:6s} event_id={earnings_event_id:3d}  {r['signal_direction']:8s}  "
              f"conf={conf_str}  evidence={r['evidence_count']:3d}  ({r['reason']})")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    run()