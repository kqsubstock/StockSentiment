"""
news_scraper.py — Pulls recent headlines for each ticker from NewsAPI's
/v2/everything endpoint and stores them in sentiment_records with
source='news'.

Mutual exclusivity with StockTwits: this scraper, and the scorer that
processes its output, are identical in shape to the StockTwits path —
finbert_vader_scorer.py has no source filter, so News rows get scored
"for free" once inserted. The actual exclusivity boundary lives in
build_confidence_trajectory.py's get_weekly_counts(), which must be
scoped to source='stocktwits' (see project notes) — until that filter
is in place, News data must NOT be run through this scraper, or it
will silently enter live trajectories/signals.

raw_text composition: title + description (NewsAPI's own 1-2 sentence
summary), NOT the `content` field — the free/Developer tier truncates
`content` to ~200 characters with a "[+N chars]" marker, so it adds
little over description while eating into the 512-character budget
finbert_vader_scorer.py's score_record() already truncates to.
Full article body is not available on this tier without a second
fetch of the article URL itself (paywalls, inconsistent HTML per
outlet) — deliberately out of scope for now.

Cursor design: NewsAPI's free tier delays articles ~24h and can return
them slightly out of publish order, so this does NOT use a hard
"since last cursor" boundary the way the original StockTwits scraper
did before its cursor bug was found. Instead, every run re-fetches a
buffer window (OVERLAP_HOURS) behind the last recorded fetch time and
relies on INSERT OR IGNORE against UNIQUE(source, source_message_id)
to dedupe. Overlap is free insurance here, not risk.

Search terms: NEWS_QUERY_TERMS below is a deliberately separate,
short-form mapping from the `companies` table's company_name column —
company_name includes legal suffixes ("Inc.", "Corp.") that hurt
recall on NewsAPI's free-text search.

Rate limits: free/Developer tier is capped at 100 requests/day. One
request per ticker per run (no pagination beyond one page of 100
articles), so 12 tickers = 12 requests/run — comfortable headroom
even at several runs/day. Currently intended to run once daily,
standalone (not wired into run_pipeline.py) until News data has been
validated the same way StockTwits was.
"""
import csv
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"
EXPORT_DIR = Path(__file__).parent.parent / "data" / "exports"
NEWSAPI_KEY = os.environ["NEWSAPI_KEY"]
API_URL = "https://newsapi.org/v2/everything"

PAGE_SIZE = 100          # NewsAPI max per page — one page per ticker per run, no
                          # further pagination for now (placeholder, revisit if a
                          # ticker's daily volume ever exceeds this)
LOOKBACK_DAYS_FIRST_RUN = 25   # free tier caps `from` at ~1 month back; stay safely inside that
OVERLAP_HOURS = 6              # see cursor design note in module docstring


# Short-form search terms — separate from companies.company_name by design (see docstring).
NEWS_QUERY_TERMS = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "META": "Meta Platforms",
    "AMZN": "Amazon",
    "TSLA": "Tesla",
    "NVDA": "Nvidia",
    "DIS": "Disney",
    "PLTR": "Palantir",
    "ABNB": "Airbnb",
    "NKE": "Nike",
    "CRWD": "CrowdStrike",
    "ADBE": "Adobe",
}


def get_active_tickers(conn):
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM companies WHERE active = 1 ORDER BY ticker")
    return [row[0] for row in cur.fetchall()]


def get_last_fetched_at(conn, ticker):
    cur = conn.cursor()
    cur.execute("SELECT last_fetched_at FROM news_cursors WHERE ticker = ?", (ticker,))
    row = cur.fetchone()
    return row[0] if row else None


def update_cursor(conn, ticker, fetched_at_iso):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO news_cursors (ticker, last_fetched_at, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(ticker) DO UPDATE SET
            last_fetched_at = excluded.last_fetched_at,
            updated_at = excluded.updated_at
    """, (ticker, fetched_at_iso))
    conn.commit()


def compute_from_dt(conn, ticker, now_utc):
    """Returns the datetime to pass as NewsAPI's `from` param. First-ever
    run for a ticker falls back to LOOKBACK_DAYS_FIRST_RUN; subsequent
    runs use the last cursor minus the overlap buffer."""
    last_fetched_at = get_last_fetched_at(conn, ticker)
    if last_fetched_at is None:
        return now_utc - timedelta(days=LOOKBACK_DAYS_FIRST_RUN)
    return datetime.fromisoformat(last_fetched_at) - timedelta(hours=OVERLAP_HOURS)


def fetch_news(query, from_dt):
    params = {
        "q": query,
        "from": from_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": PAGE_SIZE,
        "apiKey": NEWSAPI_KEY,
    }
    resp = requests.get(API_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"NewsAPI error: {data.get('message', data)}")
    return data.get("articles", [])


def parse_article(ticker, article):
    title = (article.get("title") or "").strip()
    description = (article.get("description") or "").strip()
    raw_text = f"{title}\n\n{description}" if description else title

    return {
        "ticker": ticker,
        "source": "news",
        "source_message_id": article.get("url"),   # naturally unique per article
        "timestamp": article.get("publishedAt"),    # ISO 8601 UTC — same format
                                                       # compute_week_relative.py already parses
        "raw_text": raw_text,
        "sentiment_score": None,
        "label": None,     # scored later by finbert_vader_scorer.py — same as
                             # untagged StockTwits posts, no separate scorer needed
        "scored_by": None,
    }


def insert_records(conn, records):
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT OR IGNORE INTO sentiment_records
            (ticker, source, source_message_id, timestamp, raw_text, sentiment_score, label, scored_by)
        VALUES
            (:ticker, :source, :source_message_id, :timestamp, :raw_text, :sentiment_score, :label, :scored_by)
        """,
        records,
    )
    conn.commit()
    return cur.rowcount


def export_to_csv(records, run_timestamp):
    if not records:
        return None

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = EXPORT_DIR / f"news_{run_timestamp}.csv"

    fieldnames = ["ticker", "source", "source_message_id", "timestamp",
                  "raw_text", "sentiment_score", "label", "scored_by"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    return filepath


def run():
    conn = sqlite3.connect(DB_PATH)

    cur = conn.cursor()
    cur.execute("PRAGMA table_info(news_cursors)")
    if not cur.fetchall():
        conn.close()
        raise RuntimeError(
            "news_cursors table does not exist. Run migrations/add_news_cursors_table.py first."
        )

    tickers = get_active_tickers(conn)
    now_utc = datetime.now(timezone.utc)
    run_timestamp = now_utc.strftime("%Y%m%d_%H%M%S")

    all_records = []
    requests_used = 0

    print(f"Pulling News data for {len(tickers)} tickers...\n")
    print(f"Start time: {now_utc.isoformat()}\n{'=' * 70}")

    for ticker in tickers:
        query = NEWS_QUERY_TERMS.get(ticker, ticker)
        from_dt = compute_from_dt(conn, ticker, now_utc)

        try:
            articles = fetch_news(query, from_dt)
            requests_used += 1
            records = [parse_article(ticker, a) for a in articles if a.get("url")]
            all_records.extend(records)

            print(f"  {ticker:6s} {len(records):3d} articles pulled (from={from_dt.date()})")
            update_cursor(conn, ticker, now_utc.isoformat())

        except (requests.exceptions.RequestException, RuntimeError) as e:
            print(f"  {ticker:6s} FAILED — {e}")

        time.sleep(1)  # courtesy delay, same pattern as stocktwits_scraper.py

    inserted = insert_records(conn, all_records)
    csv_path = export_to_csv(all_records, run_timestamp)

    print(f"\n{inserted} records inserted into sentiment_records (source='news').")
    print(f"NewsAPI requests used this run: {requests_used} (free tier cap: 100/day)")
    if csv_path:
        print(f"CSV export written to: {csv_path}")
        print("NOTE: rollup_exports.py currently only globs 'stocktwits_*.csv' —")
        print("      news_*.csv files will accumulate in data/exports/ uncollected")
        print("      until that script's pattern is extended, if you want that.")

    conn.close()


if __name__ == "__main__":
    run()
