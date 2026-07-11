"""
test_stocktwits_pagination.py — one-time diagnostic, safe to delete
after running.

Tests whether StockTwits' public symbol-stream endpoint honors any
page-size parameter beyond its apparent ~30-message default, and
whether the response includes cursor metadata (since/max) that could
inform incremental pagination design.

Read-only. Hits a single ticker a handful of times — well under the
200 req/hour public rate limit. Does not touch sentiment_records.
"""
from curl_cffi import requests

API_BASE = "https://api.stocktwits.com/api/2/streams/symbol"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}
TEST_TICKER = "TSLA"  # high-volume ticker — best for surfacing a real ceiling


def hit(params=None):
    url = f"{API_BASE}/{TEST_TICKER}.json"
    resp = requests.get(url, headers=HEADERS, impersonate="chrome124",
                         params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    messages = data.get("messages", [])
    cursor = data.get("cursor")
    return messages, cursor


def run():
    print(f"Testing pagination behavior against {TEST_TICKER}...\n")

    # Baseline — no params, matches current scraper behavior exactly
    baseline, cursor = hit()
    print(f"baseline (no params):  {len(baseline):3d} messages   cursor={cursor}")

    # Candidate page-size params
    for param in ["limit", "max", "count", "since"]:
        try:
            msgs, cursor = hit({param: 100})
            print(f"{param}=100:{'':>14s}{len(msgs):3d} messages   cursor={cursor}")
        except Exception as e:
            print(f"{param}=100: request failed — {e}")

    print("\nIf any of the above returned >30 messages, that param controls "
          "page size. Check the 'cursor' field above too — StockTwits often "
          "returns since/max IDs there that can be reused directly as request "
          "params for incremental pulls, without you tracking last-seen IDs "
          "in your own DB.")


if __name__ == "__main__":
    run()