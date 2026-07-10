"""
check_nvda_trajectory.py — one-time diagnostic, safe to delete after running.

Read-only. Pulls all confidence_trajectory rows for NVDA event_id=12 to
sanity-check that cumulative counts and posterior values progress
logically week to week (alpha/beta growing correctly, posterior_mean
shifting in the direction the week's bullish/bearish mix implies).
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"
EVENT_ID = 12


def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT week_relative, bullish_count, bearish_count,
               cumulative_bullish, cumulative_bearish,
               alpha, beta, posterior_mean, posterior_variance
        FROM confidence_trajectory
        WHERE earnings_event_id = ?
        ORDER BY week_relative
        """,
        (EVENT_ID,),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print(f"No confidence_trajectory rows found for earnings_event_id={EVENT_ID}.")
        return

    print(f"confidence_trajectory rows for earnings_event_id={EVENT_ID}:\n")
    header = f"{'week':>5} {'bull':>5} {'bear':>5} {'cum_bull':>9} {'cum_bear':>9} {'alpha':>7} {'beta':>7} {'mean':>7} {'variance':>10}"
    print(header)
    print("-" * len(header))
    for week, bull, bear, cum_bull, cum_bear, alpha, beta, mean, variance in rows:
        print(f"{week:>5} {bull:>5} {bear:>5} {cum_bull:>9} {cum_bear:>9} "
              f"{alpha:>7.2f} {beta:>7.2f} {mean:>7.3f} {variance:>10.5f}")


if __name__ == "__main__":
    run()