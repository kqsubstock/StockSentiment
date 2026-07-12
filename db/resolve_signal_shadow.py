"""
resolve_signal_shadow.py — Shadow classification pass: reclassifies each
earnings_event's decision-week posterior_mean using threshold bounds
centered on the Bayesian prior (0.53) instead of the production
thresholds centered on 0.50, and stores the result separately without
touching signal_direction or confidence_score.

This exists to answer a specific open question: how much of the
project's persistent all-bullish signal skew is real predictive signal
vs. an artifact of threshold placement relative to the prior mean.
Production thresholds (0.65 / 0.35) are symmetric around 0.50, but the
prior mean is 0.53 — so a bullish call only needs to clear the prior by
0.12, while a bearish call needs to clear it by 0.18 in the other
direction. This asymmetry alone could partially explain why bearish
signals have never once fired, independent of anything about the
underlying sentiment data itself.

Shadow thresholds keep the same total width (0.30) as production but
recenter it on the prior mean: bullish >= 0.68, bearish <= 0.38.

Reuses get_all_earnings_events() and get_signal_as_of_week() from
resolve_signal.py rather than duplicating the lookup logic — the
evidence floor (MIN_EVIDENCE) and decision week (DECISION_WEEK) are
intentionally identical to production. Only the classification cutoffs
differ, since this is a test of threshold geometry, not a different
model or a different evidence-sufficiency rule.

PURELY ANALYTICAL. shadow_signal_direction is never read by anything
that touches paper trading, strike selection, or resolve_signal.py's
own output, and this script is NOT wired into run_pipeline.py. Do not
add it to the daily pipeline or let it influence a trade decision
without an explicit decision to do so — treat it as a monitoring
column for the calibration review, not a competing signal source.

Safe to re-run: recomputes every event from scratch each time, same
pattern as resolve_signal.py.

Requires add_shadow_signal_column.py to have been run once first.
"""
import sqlite3
from pathlib import Path

from resolve_signal import (
    get_all_earnings_events,
    get_signal_as_of_week,
    DECISION_WEEK,
    MIN_EVIDENCE,
)

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"

# Same total width (0.30) as production thresholds, recentered on the
# prior mean (0.53) instead of 0.50.
SHADOW_BULLISH_THRESHOLD = 0.68
SHADOW_BEARISH_THRESHOLD = 0.38


def classify_shadow(evidence_count, posterior_mean):
    if evidence_count < MIN_EVIDENCE:
        return "no_bet"
    if posterior_mean >= SHADOW_BULLISH_THRESHOLD:
        return "bullish"
    if posterior_mean <= SHADOW_BEARISH_THRESHOLD:
        return "bearish"
    return "no_bet"


def resolve_event_shadow(conn, earnings_event_id):
    row = get_signal_as_of_week(conn, earnings_event_id, DECISION_WEEK)
    if row is None:
        return "no_bet", 0

    week_used, cum_bullish, cum_bearish, posterior_mean = row
    evidence_count = cum_bullish + cum_bearish
    shadow_direction = classify_shadow(evidence_count, posterior_mean)
    return shadow_direction, evidence_count


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(earnings_events)")
    if "shadow_signal_direction" not in {row[1] for row in cur.fetchall()}:
        conn.close()
        raise RuntimeError(
            "earnings_events.shadow_signal_direction does not exist. "
            "Run migrations/add_shadow_signal_column.py first."
        )

    events = get_all_earnings_events(conn)
    print(f"Running shadow classification for {len(events)} earnings events "
          f"(bullish>={SHADOW_BULLISH_THRESHOLD}, bearish<={SHADOW_BEARISH_THRESHOLD})...\n")

    disagreements = []

    for earnings_event_id, ticker in events:
        shadow_direction, evidence_count = resolve_event_shadow(conn, earnings_event_id)

        cur.execute(
            "UPDATE earnings_events SET shadow_signal_direction = ? WHERE id = ?",
            (shadow_direction, earnings_event_id),
        )

        cur.execute(
            "SELECT signal_direction, confidence_score FROM earnings_events WHERE id = ?",
            (earnings_event_id,),
        )
        prod_direction, conf = cur.fetchone()

        conf_str = f"{conf:.3f}" if conf is not None else "  N/A"
        flag = ""
        if evidence_count > 0 and prod_direction != shadow_direction:
            flag = "  <- DISAGREES with production"
            disagreements.append((ticker, earnings_event_id, prod_direction, shadow_direction, conf))

        print(f"  {ticker:6s} event_id={earnings_event_id:3d}  "
              f"prod={prod_direction:8s} shadow={shadow_direction:8s}  "
              f"conf={conf_str}  evidence={evidence_count:3d}{flag}")

    conn.commit()

    print(f"\n{len(disagreements)} event(s) where shadow thresholds disagree with production:")
    for ticker, event_id, prod_direction, shadow_direction, conf in disagreements:
        conf_str = f"{conf:.3f}" if conf is not None else "  N/A"
        print(f"  {ticker:6s} event_id={event_id:3d}  "
              f"prod={prod_direction:8s} -> shadow={shadow_direction:8s}  (conf={conf_str})")

    if not disagreements:
        print("  None — every event's classification held under both threshold sets.")

    conn.close()


if __name__ == "__main__":
    run()
