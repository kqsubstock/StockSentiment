"""
build_confidence_trajectory.py — Builds the confidence_trajectory table:
a running Beta-Binomial posterior (alpha, beta, mean, variance) for each
earnings_event, walked week by week from week_relative -18 through -1.

Each event starts from the same seeded prior (alpha=5.3, beta=4.7 — mean
0.53, matching the project's stated 0.52-0.55 base rate, weighted as
~10 pseudo-observations). Priors do NOT carry over between an event and
its predecessor for the same ticker — each earnings season is treated as
an independent question.

Only bullish/bearish sentiment_records count as evidence; neutral rows
are excluded entirely (per design decision — neutral weeks contribute
no directional evidence rather than being treated as weak/split votes).

Only weeks where bullish_count or bearish_count is nonzero produce a
row — weeks with no qualifying evidence are skipped rather than storing
a duplicate of the prior week's unchanged posterior. Downstream readers
must forward-fill gaps at query/plot time.

Safe to re-run: INSERT OR IGNORE against UNIQUE(earnings_event_id,
week_relative), so re-running after fresh scraping only adds new rows
for weeks that now have qualifying data.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"

PRIOR_ALPHA = 5.3
PRIOR_BETA = 4.7

WEEK_START = -18
WEEK_END = -1


def get_all_earnings_events(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, ticker FROM earnings_events ORDER BY ticker, earnings_date")
    return cur.fetchall()


def get_weekly_counts(conn, earnings_event_id):
    """Returns {week_relative: (bullish_count, bearish_count)} for one event."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT week_relative,
               SUM(CASE WHEN label = 'bullish' THEN 1 ELSE 0 END),
               SUM(CASE WHEN label = 'bearish' THEN 1 ELSE 0 END)
        FROM sentiment_records
        WHERE earnings_event_id = ?
          AND week_relative BETWEEN ? AND ?
          AND label IN ('bullish', 'bearish')
        GROUP BY week_relative
        """,
        (earnings_event_id, WEEK_START, WEEK_END),
    )
    return {week: (bullish, bearish) for week, bullish, bearish in cur.fetchall()}


def compute_posterior(alpha, beta):
    mean = alpha / (alpha + beta)
    variance = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
    return mean, variance


def build_trajectory_for_event(conn, earnings_event_id):
    weekly_counts = get_weekly_counts(conn, earnings_event_id)

    cumulative_bullish = 0
    cumulative_bearish = 0
    rows_to_insert = []

    for week in range(WEEK_START, WEEK_END + 1):
        bullish_count, bearish_count = weekly_counts.get(week, (0, 0))

        if bullish_count == 0 and bearish_count == 0:
            continue  # no new evidence this week — skip, per design decision

        cumulative_bullish += bullish_count
        cumulative_bearish += bearish_count

        alpha = PRIOR_ALPHA + cumulative_bullish
        beta = PRIOR_BETA + cumulative_bearish
        posterior_mean, posterior_variance = compute_posterior(alpha, beta)

        rows_to_insert.append((
            earnings_event_id, week, bullish_count, bearish_count,
            cumulative_bullish, cumulative_bearish,
            alpha, beta, posterior_mean, posterior_variance,
        ))

    return rows_to_insert


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    events = get_all_earnings_events(conn)
    print(f"Building confidence trajectories for {len(events)} earnings events...\n")

    total_rows_inserted = 0
    events_with_data = 0

    for earnings_event_id, ticker in events:
        rows = build_trajectory_for_event(conn, earnings_event_id)

        if rows:
            events_with_data += 1
            cur.executemany(
                """
                INSERT OR IGNORE INTO confidence_trajectory
                    (earnings_event_id, week_relative, bullish_count, bearish_count,
                     cumulative_bullish, cumulative_bearish, alpha, beta,
                     posterior_mean, posterior_variance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            total_rows_inserted += cur.rowcount
            final_mean = rows[-1][8]
            print(f"  {ticker:6s} event_id={earnings_event_id:4d}  "
                  f"{len(rows)} weeks with evidence, latest posterior_mean={final_mean:.3f}")

    conn.commit()

    print(f"\n{events_with_data}/{len(events)} events had at least one week of evidence.")
    print(f"{total_rows_inserted} rows inserted into confidence_trajectory.")

    conn.close()


if __name__ == "__main__":
    run()