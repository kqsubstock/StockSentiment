"""
resolve_earnings_outcomes.py — Fills in actual_outcome and actual_move_pct
for earnings_events whose reaction window has passed.

Reaction window: pre-close (last trading day strictly before the earnings
cutoff) vs reaction-close (first trading day at or after the cutoff).
Uses the shared earnings_cutoff module — same cutoff definition as
compute_week_relative.py.

Classification: actual_move_pct > +3%  -> up
                actual_move_pct < -3%  -> down
                otherwise              -> flat
(+/-3% is a placeholder threshold, deliberately uniform across tickers
for now — revisit once enough real actual_move_pct values exist to look
at the distribution, since low-vol names like AAPL/NKE and high-vol
names like TSLA/PLTR probably don't belong under the same band.)

pnl is NOT touched here — that stays manual entry from Webull fills.

Safe to re-run: only touches events where actual_outcome IS NULL or
'pending'. Events whose cutoff hasn't happened yet, or where trading
data isn't available yet on both sides of the cutoff, are left pending.
"""
import datetime as dt
import sqlite3
from datetime import timedelta
from pathlib import Path

import yfinance as yf

from earnings_cutoff import compute_cutoff_utc

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"

FLAT_THRESHOLD = 0.03  # placeholder — revisit once real move data exists


def get_unresolved_events(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, ticker, earnings_date, report_time
        FROM earnings_events
        WHERE actual_outcome IS NULL OR actual_outcome = 'pending'
        ORDER BY earnings_date, ticker
        """
    )
    return cur.fetchall()


def get_price_window(ticker, cutoff_utc):
    """Pulls a small window of daily closes around the cutoff and returns
    (pre_close, reaction_close), or (None, None) if there isn't enough
    trading-day data on both sides yet."""
    start = (cutoff_utc - timedelta(days=7)).date()
    end = (cutoff_utc + timedelta(days=7)).date()

    hist = yf.Ticker(ticker).history(start=start, end=end, interval="1d")
    if hist.empty:
        return None, None

    if hist.index.tz is None:
        hist.index = hist.index.tz_localize("America/New_York")

    cutoff_local = cutoff_utc.astimezone(hist.index.tz)

    pre = hist[hist.index < cutoff_local]
    post = hist[hist.index >= cutoff_local]

    if pre.empty or post.empty:
        return None, None

    return pre["Close"].iloc[-1], post["Close"].iloc[0]


def classify(pct_change):
    if pct_change > FLAT_THRESHOLD:
        return "up"
    elif pct_change < -FLAT_THRESHOLD:
        return "down"
    return "flat"


def resolve_event(ticker, earnings_date, report_time):
    cutoff_utc = compute_cutoff_utc(earnings_date, report_time)

    if cutoff_utc > dt.datetime.now(dt.timezone.utc):
        return None  # hasn't happened yet

    pre_close, reaction_close = get_price_window(ticker, cutoff_utc)
    if pre_close is None:
        return None  # not enough data yet

    pct_change = (reaction_close - pre_close) / pre_close
    return classify(pct_change), round(pct_change * 100, 2)


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    events = get_unresolved_events(conn)
    print(f"Checking {len(events)} unresolved earnings events...\n")

    resolved_count = 0
    for event_id, ticker, earnings_date, report_time in events:
        result = resolve_event(ticker, earnings_date, report_time)

        if result is None:
            print(f"  {ticker:6s} {earnings_date}  -- still pending")
            continue

        outcome, move_pct = result
        cur.execute(
            "UPDATE earnings_events SET actual_outcome = ?, actual_move_pct = ? WHERE id = ?",
            (outcome, move_pct, event_id),
        )
        resolved_count += 1
        print(f"  {ticker:6s} {earnings_date}  {outcome:5s}  {move_pct:+.2f}%")

    conn.commit()
    conn.close()
    print(f"\nResolved {resolved_count} of {len(events)} checked events.")


if __name__ == "__main__":
    run()