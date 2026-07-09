CREATE TABLE IF NOT EXISTS companies (
    ticker                  TEXT PRIMARY KEY,
    company_name            TEXT NOT NULL,
    sector                  TEXT NOT NULL,
    fiscal_window           TEXT NOT NULL,                          --'jan_apr_jul_oct' | 'feb_may_aug_nov' | 'mar_jun_sep_dec'
    active                  INTEGER NOT NULL DEFAULT 1,              -- 1 = currently traacked, 0 = dropped from roster
    date_added              TEXT NOT NULL DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS sentiment_records (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker                  TEXT NOT NULL REFERENCES companies(ticker),
    source                  TEXT NOT NULL CHECK (source IN ('stocktwits', 'reddit', 'news', 'google_trends')),
    source_message_id       TEXT,   
    timestamp               TEXT NOT NULL,
    raw_text                TEXT,
    sentiment_score         REAL,
    label                   TEXT CHECK (label IN ('bullish', 'bearish', 'neutral')),
    week_relative           INTEGER,
    earnings_event_id       INTEGER REFERENCES earnings_events(id),
    scored_by               TEXT,
    date_collected          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, source_message_id)
);

CREATE TABLE IF NOT EXISTS earnings_events (
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

CREATE TABLE IF NOT EXISTS source_accuracy (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker                  TEXT NOT NULL REFERENCES companies(ticker),
    source                  TEXT NOT NULL CHECK (source IN ('stocktwits', 'reddit', 'news', 'google_trends')),
    period_start            TEXT NOT NULL,
    period_end              TEXT NOT NULL,
    total_signals           INTEGER NOT NULL DEFAULT 0,
    correct_direction       INTEGER NOT NULL DEFAULT 0,
    accuracy_pct            REAL,
    last_updated            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sentiment_ticker_time ON sentiment_records(ticker, timestamp);
CREATE INDEX IF NOT EXISTS idx_earnings_ticker_date ON earnings_events(ticker, earnings_date);