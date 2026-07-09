"""
init_db.py - Creates the SQLite database from schema.sql and seeds the
companies reference table with the finalized 12-ticker roster.

Run this once to set up the database, and again any time you want to
reset the schema (it uses CREATE TABLE IF NOT EXISTS, so it's safe to
re-run without wiping existing sentiment/earnings data).
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Finalized 12-ticker roster with sector and fiscal reporting window.
# fiscal_window groups tickers by which earnings-season week they tend
# to cluster in — useful later for sanity-checking calendar spread and
# flagging when two tickers in the same window report in the same week
# (correlated macro exposure).
COMPANIES = [
    # ticker, company_name, sector, fiscal_window
    ("AAPL", "Apple Inc.", "Consumer Tech", "jan_apr_jul_oct"),
    ("MSFT", "Microsoft Corp.", "Software/Cloud", "jan_apr_jul_oct"),
    ("META", "Meta Platforms Inc.", "Social/Advertising", "jan_apr_jul_oct"),
    ("AMZN", "Amazon.com Inc.", "E-commerce/Cloud", "jan_apr_jul_oct"),
    ("TSLA", "Tesla Inc.", "Automotive/EV", "jan_apr_jul_oct"),
    ("NVDA", "NVIDIA Corp.", "Semiconductors", "feb_may_aug_nov"),
    ("DIS", "The Walt Disney Company", "Media/Entertainment", "feb_may_aug_nov"),
    ("PLTR", "Palantir Technologies", "AI/Gov Tech", "feb_may_aug_nov"),
    ("ABNB", "Airbnb Inc.", "Travel/Consumer Discretionary", "feb_may_aug_nov"),
    ("NKE", "Nike Inc.", "Apparel/Retail", "mar_jun_sep_dec"),
    ("CRWD", "CrowdStrike Holdings", "Cybersecurity", "mar_jun_sep_dec"),
    ("ADBE", "Adobe Inc.", "Software", "mar_jun_sep_dec"),
]


def init_database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    with open(SCHEMA_PATH, "r") as f:
        cur.executescript(f.read())

    cur.executemany(
        """
        INSERT OR IGNORE INTO companies (ticker, company_name, sector, fiscal_window)
        VALUES (?, ?, ?, ?)
        """,
        COMPANIES,
    )

    conn.commit()

    # Sanity check output — confirms what actually landed in the table
    cur.execute("SELECT ticker, sector, fiscal_window FROM companies ORDER BY fiscal_window, ticker")
    rows = cur.fetchall()
    print(f"Database initialized at: {DB_PATH}")
    print(f"Companies seeded: {len(rows)}\n")
    for ticker, sector, window in rows:
        print(f"  {ticker:6s} {sector:35s} {window}")

    conn.close()


if __name__ == "__main__":
    init_database()