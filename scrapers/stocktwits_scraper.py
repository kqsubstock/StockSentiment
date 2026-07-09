"""
stocktwits_scraper.py — Pulls recent messages for each ticker from
StockTwits' public symbol-stream API and stores them in sentiment_records.

Rate limits: StockTwits' public API is capped at 200 requests/hour
per IP for unauthenticated access. With 12 tickers, one full pass
uses 12 requests — plenty of headroom to run this several times a day.
"""

import sqlite3
from curl_cffi import requests
import time
import csv
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"
EXPORT_DIR = Path(__file__).parent.parent / "data" / "exports"
API_BASE = "https://api.stocktwits.com/api/2/streams/symbol"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

# StockTwits' own bullish/bearish tag maps directly onto our label field.
# Untagged messages (a large share of posts) get label=None here —
# those get scored later by VADER/FinBERT in Phase 3, not by this scraper.
SENTIMENT_MAP = {
    "Bullish": ("bullish", 1.0),
    "Bearish": ("bearish", -1.0),
}


def get_active_tickers(conn):
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM companies WHERE active = 1 ORDER BY ticker")
    return [row[0] for row in cur.fetchall()]


def fetch_stocktwits_messages(ticker):
    """Hits the public symbol stream endpoint for one ticker."""
    url = f"{API_BASE}/{ticker}.json"
    resp = requests.get(url, headers=HEADERS, impersonate="chrome124", timeout=10)
    resp.raise_for_status()
    return resp.json().get("messages", [])


def parse_message(ticker, msg):
    """Maps a raw StockTwits message into our sentiment_records row shape."""
    entities = msg.get("entities", {}) or {}
    sentiment_obj = entities.get("sentiment")
    tag = sentiment_obj.get("basic") if sentiment_obj else None

    if tag in SENTIMENT_MAP:
        label, score = SENTIMENT_MAP[tag]
        scored_by = "stocktwits_label"
    else:
        # Untagged post — leave scoring to the FinBERT/VADER pass (Phase 3)
        label, score = None, None
        scored_by = None

    return {
        "ticker": ticker,
        "source": "stocktwits",
        "timestamp": msg["created_at"],
        "raw_text": msg["body"],
        "sentiment_score": score,
        "label": label,
        "scored_by": scored_by,
    }

def insert_records(conn, records):
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT INTO sentiment_records
            (ticker, source, timestamp, raw_text, sentiment_score, label, scored_by)
        VALUES
            (:ticker, :source, :timestamp, :raw_text, :sentiment_score, :label, :scored_by)
        """,
        records,
    )
    conn.commit()
    return cur.rowcount


def export_to_csv(records, run_timestamp):
    """
    Writes a plain CSV of this run's pull to data/exports/ so you can
    open it directly in Excel without touching the database at all.
    """
    if not records:
        return None

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"stocktwits_{run_timestamp}.csv"
    filepath = EXPORT_DIR / filename

    fieldnames = ["ticker", "source", "timestamp", "raw_text", "sentiment_score", "label", "scored_by"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    return filepath


def run():
    conn = sqlite3.connect(DB_PATH)
    tickers = get_active_tickers(conn)
    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    all_records = []
    print(f"Pulling StockTwits data for {len(tickers)} tickers...\n")

    for ticker in tickers:
        try:
            messages = fetch_stocktwits_messages(ticker)
            records = [parse_message(ticker, m) for m in messages]
            all_records.extend(records)

            labeled = sum(1 for r in records if r["label"] is not None)
            print(f"  {ticker:6s} {len(records):3d} messages pulled ({labeled} pre-labeled)")

        except requests.exceptions.RequestException as e:
            print(f"  {ticker:6s} FAILED — {e}")

        # Courtesy delay between requests — well under the rate limit,
        # but avoids hammering the endpoint in a tight loop.
        time.sleep(1)

    inserted = insert_records(conn, all_records)
    csv_path = export_to_csv(all_records, run_timestamp)

    print(f"\n{inserted} records inserted into sentiment_records.")
    if csv_path:
        print(f"CSV export written to: {csv_path}")

    conn.close()


if __name__ == "__main__":
    run()