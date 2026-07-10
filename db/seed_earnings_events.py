"""
seed_earnings_events.py — Inserts known/estimated earnings dates for the
12-ticker roster into earnings_events. Safe to re-run: uses INSERT OR
IGNORE against the UNIQUE(ticker, earnings_date) constraint, so already-
seeded rows are skipped rather than duplicated.

Sourcing notes:
- Dates pulled primarily from company SEC 8-K filings where available
  (most reliable — company's own words), cross-checked against
  TipRanks/MarketChameleon for report_time (BMO/AMC).
- date_confirmed=1 means the company has officially announced/reported
  this date. date_confirmed=0 means it's an analyst/aggregator estimate
  that could still shift — currently true for PLTR and ABNB's next
  (Q2 2026) dates, where sources disagreed on the exact day.
- report_time='unknown' where sources didn't specify BMO/AMC.

Re-check the date_confirmed=0 rows closer to their earnings date before
relying on them for signal generation or strike selection.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"

# ticker, earnings_date (YYYY-MM-DD), report_time, date_confirmed, fiscal_quarter
EARNINGS_EVENTS = [
    ("AAPL", "2026-01-29", "AMC", 1, "Q1 FY26"),
    ("AAPL", "2026-04-30", "AMC", 1, "Q2 FY26"),
    ("AAPL", "2026-07-30", "AMC", 1, "Q3 FY26"),

    ("MSFT", "2026-04-29", "AMC", 1, "Q3 FY26"),

    ("META", "2026-04-29", "AMC", 1, "Q1 2026"),

    ("AMZN", "2026-04-29", "AMC", 1, "Q1 2026"),

    ("TSLA", "2026-01-28", "AMC", 1, "Q4 2025"),
    ("TSLA", "2026-04-22", "AMC", 1, "Q1 2026"),
    ("TSLA", "2026-07-22", "AMC", 1, "Q2 2026"),

    ("NVDA", "2026-02-25", "unknown", 1, "Q4 FY26"),
    ("NVDA", "2026-05-20", "AMC", 1, "Q1 FY27"),
    ("NVDA", "2026-08-26", "AMC", 1, "Q2 FY27"),

    ("DIS", "2026-02-02", "BMO", 1, "Q1 FY26"),
    ("DIS", "2026-05-05", "BMO", 1, "Q2 FY26"),
    ("DIS", "2026-08-12", "AMC", 1, "Q3 FY26"),

    ("PLTR", "2026-05-04", "AMC", 1, "Q1 2026"),
    ("PLTR", "2026-08-03", "AMC", 0, "Q2 2026"),  # unconfirmed — sources disagree (Aug 3 vs Aug 10)

    ("ABNB", "2026-02-12", "unknown", 1, "Q4 2025"),
    ("ABNB", "2026-05-07", "AMC", 1, "Q1 2026"),
    ("ABNB", "2026-08-05", "AMC", 0, "Q2 2026"),  # unconfirmed — sources disagree (Aug 5 vs Aug 12)

    ("NKE", "2026-04-02", "AMC", 1, "Q3 FY26"),
    ("NKE", "2026-06-30", "AMC", 1, "Q4 FY26"),

    ("CRWD", "2026-03-03", "unknown", 1, "Q4 FY26"),
    ("CRWD", "2026-06-03", "unknown", 1, "Q1 FY27"),
    ("CRWD", "2026-09-02", "AMC", 1, "Q2 FY27"),

    ("ADBE", "2026-03-12", "unknown", 1, "Q1 FY26"),
    ("ADBE", "2026-06-11", "AMC", 1, "Q2 FY26"),
    ("ADBE", "2026-09-10", "AMC", 1, "Q3 FY26"),

    ("META", "2026-01-28", "unknown", 1, "Q4 2025"),
    ("MSFT", "2026-07-29", "AMC", 0, "Q4 FY26"),  # unconfirmed — sources conflict (Jul 28 vs Jul 29)
    ("META", "2026-07-29", "AMC", 0, "Q2 2026"),  # unconfirmed — analyst estimate
    ("AMZN", "2026-07-30", "AMC", 0, "Q2 2026"),  # unconfirmed — WSH explicitly flags unconfirmed
    ("NKE", "2026-09-29", "AMC", 0, "Q1 FY27"),  # unconfirmed — projected date
]


def seed_earnings_events():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.executemany(
        """
        INSERT OR IGNORE INTO earnings_events
            (ticker, earnings_date, report_time, date_confirmed, fiscal_quarter)
        VALUES (?, ?, ?, ?, ?)
        """,
        EARNINGS_EVENTS,
    )
    inserted = cur.rowcount
    conn.commit()

    # Sanity check — show what's actually in the table now, oldest first
    cur.execute(
        """
        SELECT ticker, earnings_date, report_time, date_confirmed, fiscal_quarter
        FROM earnings_events
        ORDER BY earnings_date, ticker
        """
    )
    rows = cur.fetchall()

    print(f"Seed complete. {len(EARNINGS_EVENTS)} rows attempted.")
    print(f"{len(rows)} total rows now in earnings_events.\n")
    for ticker, date, report_time, confirmed, quarter in rows:
        flag = "" if confirmed else "  <- UNCONFIRMED"
        print(f"  {ticker:6s} {date}  {report_time:8s} {quarter:10s}{flag}")

    conn.close()


if __name__ == "__main__":
    seed_earnings_events()