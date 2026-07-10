"""
pull_iv_history.py — Daily snapshot of ATM implied volatility per ticker.
Builds the historical IV series needed for IV rank calculations later.
"""
import os
import sqlite3
import requests
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"
TRADIER_TOKEN = os.environ["TRADIER_TOKEN"]
BASE_URL = "https://api.tradier.com/v1"

TICKERS = ["AAPL", "MSFT", "META", "AMZN", "TSLA", "NVDA", "DIS", "PLTR", "ABNB", "NKE", "CRWD", "ADBE"]

HEADERS = {
    "Authorization": f"Bearer {TRADIER_TOKEN}",
    "Accept": "application/json"
}

IV_SANITY_CEILING = 2.0
MAX_STRIKES_OUT = 5


def get_spot_price(ticker):
    resp = requests.get(f"{BASE_URL}/markets/quotes", headers=HEADERS, params={"symbols": ticker})
    resp.raise_for_status()
    quote = resp.json()["quotes"]["quote"]
    return quote["last"]


def get_nearest_expiration(ticker):
    resp = requests.get(f"{BASE_URL}/markets/options/expirations", headers=HEADERS, params={"symbol": ticker})
    resp.raise_for_status()
    dates = resp.json()["expirations"]["date"]
    today = date.today()
    future_dates = [d for d in dates if date.fromisoformat(d) > today]
    return future_dates[0] if future_dates else None


def get_chain(ticker, expiration):
    resp = requests.get(
        f"{BASE_URL}/markets/options/chains",
        headers=HEADERS,
        params={"symbol": ticker, "expiration": expiration, "greeks": "true"}
    )
    resp.raise_for_status()
    return resp.json()["options"]["option"]


def is_strike_valid(contract):
    if contract.get("open_interest", 0) <= 0:
        return False
    if contract.get("bid", 0) <= 0:
        return False
    greeks = contract.get("greeks") or {}
    mid_iv = greeks.get("mid_iv")
    if mid_iv is None or mid_iv <= 0 or mid_iv >= IV_SANITY_CEILING:
        return False
    return True


def find_atm_with_guard(chain, spot_price):
    strikes = sorted(set(c["strike"] for c in chain))
    strikes_by_distance = sorted(strikes, key=lambda s: abs(s - spot_price))

    checked = 0
    for strike in strikes_by_distance:
        if checked >= MAX_STRIKES_OUT:
            break
        candidates = [c for c in chain if c["strike"] == strike and c["option_type"] == "call"]
        if not candidates:
            checked += 1
            continue
        contract = candidates[0]
        if is_strike_valid(contract):
            return contract
        checked += 1

    return None


def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    today_str = date.today().isoformat()

    for ticker in TICKERS:
        try:
            spot = get_spot_price(ticker)
            expiration = get_nearest_expiration(ticker)
            if not expiration:
                print(f"{ticker}: no upcoming expiration found, skipping.")
                continue

            chain = get_chain(ticker, expiration)
            atm_contract = find_atm_with_guard(chain, spot)

            if atm_contract is None:
                print(f"{ticker}: no liquid ATM strike found, skipping.")
                continue

            atm_iv = atm_contract["greeks"]["mid_iv"]
            strike_used = atm_contract["strike"]
            dte = (date.fromisoformat(expiration) - date.today()).days

            cur.execute("""
                INSERT OR REPLACE INTO iv_history
                (ticker, date, atm_iv, spot_price, dte, expiration_used, strike_used, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'tradier')
            """, (ticker, today_str, atm_iv, spot, dte, expiration, strike_used))

            print(f"{ticker}: atm_iv={atm_iv:.4f}, spot={spot}, strike_used={strike_used}, dte={dte}")

        except Exception as e:
            print(f"{ticker}: FAILED — {e}")
            continue

    conn.commit()
    conn.close()


if __name__ == "__main__":
    run()