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


def get_last_since_id(conn, ticker):
    """Returns the stored high-water-mark ID for this ticker, or None
    if it's never been scraped (first-run case)."""
    cur = conn.cursor()
    cur.execute("SELECT last_since_id FROM ticker_cursors WHERE ticker = ?", (ticker,))
    row = cur.fetchone()
    return row[0] if row else None


def update_cursor(conn, ticker, newest_id):
    """Upserts the new high-water mark after a successful pull."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ticker_cursors (ticker, last_since_id, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(ticker) DO UPDATE SET
            last_since_id = excluded.last_since_id,
            updated_at = excluded.updated_at
    """, (ticker, newest_id))
    conn.commit()


def get_active_tickers(conn):
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM companies WHERE active = 1 ORDER BY ticker")
    return [row[0] for row in cur.fetchall()]


def fetch_stocktwits_messages(ticker, since_id=None, max_id=None):
    """One request to the symbol stream endpoint. Passing neither param
    matches original baseline behavior (most recent ~30, no cursor)."""
    url = f"{API_BASE}/{ticker}.json"
    params = {}
    if since_id is not None:
        params["since"] = since_id
    if max_id is not None:
        params["max"] = max_id

    resp = requests.get(url, headers=HEADERS, impersonate="chrome124",
                         params=params or None, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data.get("messages", []), data.get("cursor", {})


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
        "source_message_id": str(msg["id"]),
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
    """
    Writes a plain CSV of this run's pull to data/exports/ so you can
    open it directly in Excel without touching the database at all.
    """
    if not records:
        return None

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"stocktwits_{run_timestamp}.csv"
    filepath = EXPORT_DIR / filename

    fieldnames = ["ticker", "source", "source_message_id", "timestamp", "raw_text", "sentiment_score", "label", "scored_by"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    return filepath


MAX_PAGES = 10  # safety cap — 10 * 30 = 300 messages per ticker per run

def fetch_all_new_messages(ticker, since_id):
    """
    Pulls everything newer than since_id, paging backward through
    the gap in ~30-message batches if there's more than one page's
    worth. Stops as soon as a page's oldest message reaches or
    passes since_id — NOT when the API's 'more' flag runs out, since
    StockTwits almost always has older history and 'more' rarely
    goes False on its own.

    Returns (messages, newest_id_seen, pages_pulled).
    newest_id_seen is None if nothing new came back at all.
    """
    all_messages = []
    newest_id_seen = None
    max_id = None
    pages_pulled = 0
    since_id_int = int(since_id) if since_id is not None else None

    while pages_pulled < MAX_PAGES:
        messages, cursor = fetch_stocktwits_messages(ticker, since_id=since_id, max_id=max_id)
        pages_pulled += 1

        if not messages:
            break

        if newest_id_seen is None:
            # Only the FIRST page's top message is the new high-water
            # mark — later pages are older, backfilled messages.
            newest_id_seen = str(messages[0]["id"])

        if since_id_int is not None:
            # Keep only messages strictly newer than the floor —
            # a page can straddle the floor, part new / part already-seen.
            in_range = [m for m in messages if int(m["id"]) > since_id_int]
            all_messages.extend(in_range)

            oldest_in_page = min(int(m["id"]) for m in messages)
            if oldest_in_page <= since_id_int:
                # Walked back past everything new — stop here regardless
                # of what cursor['more'] says.
                break
        else:
            # First-ever run for this ticker — no floor to check against,
            # original backfill-until-more-runs-out behavior applies.
            all_messages.extend(messages)

        if not cursor.get("more"):
            break

        max_id = cursor.get("max")
        if max_id is None:
            break

        time.sleep(1)  # courtesy delay between pages, same as between tickers

    if pages_pulled >= MAX_PAGES:
        print(f"  {ticker:6s} WARNING — hit {MAX_PAGES}-page cap, may not be fully caught up")

    return all_messages, newest_id_seen, pages_pulled


def run():
    conn = sqlite3.connect(DB_PATH)
    tickers = get_active_tickers(conn)
    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    all_records = []
    print(f"Pulling StockTwits data for {len(tickers)} tickers...\n")

    for ticker in tickers:
        try:
            since_id = get_last_since_id(conn, ticker)
            messages, newest_id_seen, pages_pulled = fetch_all_new_messages(ticker, since_id)
            records = [parse_message(ticker, m) for m in messages]
            all_records.extend(records)

            labeled = sum(1 for r in records if r["label"] is not None)
            print(f"  {ticker:6s} {len(records):3d} messages pulled ({labeled} pre-labeled, {pages_pulled} page{'s' if pages_pulled != 1 else ''})")

            if newest_id_seen is not None:
                update_cursor(conn, ticker, newest_id_seen)

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