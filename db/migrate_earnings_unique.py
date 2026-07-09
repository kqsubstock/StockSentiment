# migrate_earnings_unique.py — one-time migration, safe to delete after running
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"

if not DB_PATH.exists():
    raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = OFF")

conn.executescript("""
    CREATE TABLE earnings_events_new (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker                  TEXT NOT NULL REFERENCES companies(ticker),
        earnings_date           TEXT NOT NULL,
        report_time             TEXT CHECK (report_time IN ('BMO', 'AMC', 'unknown')) DEFAULT 'unknown',
        date_confirmed          INTEGER NOT NULL DEFAULT 0,
        fiscal_quarter          TEXT,
        signal_direction        TEXT CHECK (signal_direction IN ('bullish', 'bearish', 'neutral', 'no_bet')),
        confidence_score        REAL,
        strikes_selected        TEXT,
        premium_paid            REAL,
        fill_price_type         TEXT DEFAULT 'mid',
        expected_move           REAL,
        iv_rank                 REAL,
        actual_outcome          TEXT CHECK (actual_outcome IN ('up', 'down', 'flat', 'pending')),
        actual_move_pct         REAL,
        pnl                     REAL,
        was_pass                INTEGER NOT NULL DEFAULT 0,
        macro_overlap_flag      INTEGER NOT NULL DEFAULT 0,
        notes                   TEXT,
        date_logged             TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(ticker, earnings_date)
    );

    INSERT INTO earnings_events_new
        (id, ticker, earnings_date, report_time, date_confirmed, fiscal_quarter,
         signal_direction, confidence_score, strikes_selected, premium_paid,
         fill_price_type, expected_move, iv_rank, actual_outcome, actual_move_pct,
         pnl, was_pass, macro_overlap_flag, notes, date_logged)
    SELECT
        id, ticker, earnings_date, report_time, date_confirmed, fiscal_quarter,
        signal_direction, confidence_score, strikes_selected, premium_paid,
        fill_price_type, expected_move, iv_rank, actual_outcome, actual_move_pct,
        pnl, was_pass, macro_overlap_flag, notes, date_logged
    FROM earnings_events;

    DROP TABLE earnings_events;
    ALTER TABLE earnings_events_new RENAME TO earnings_events;

    CREATE INDEX IF NOT EXISTS idx_earnings_ticker_date ON earnings_events(ticker, earnings_date);
""")

conn.commit()
conn.close()
print("Migration complete: UNIQUE(ticker, earnings_date) added to earnings_events.")