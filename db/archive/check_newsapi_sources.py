"""
check_everything_sources.py — one-time diagnostic, safe to delete after running.

Hits NewsAPI's /v2/everything endpoint (the one news_scraper.py actually
uses) with a couple of real ticker queries, and prints the distinct
publisher names in the response — to see what's actually reachable
through free-text search, since /v2/top-headlines/sources describes an
unrelated curated list and doesn't reflect this.

Read-only — a handful of GET requests, does not touch the database.
"""
import os
from collections import Counter
import requests
from dotenv import load_dotenv

load_dotenv()

NEWSAPI_KEY = os.environ["NEWSAPI_KEY"]
API_URL = "https://newsapi.org/v2/everything"

TEST_QUERIES = ["Apple", "Tesla", "Nvidia"]  # a small sample of your real NEWS_QUERY_TERMS


def run():
    for query in TEST_QUERIES:
        resp = requests.get(API_URL, params={
            "q": query, "language": "en", "sortBy": "publishedAt",
            "pageSize": 100, "apiKey": NEWSAPI_KEY,
        })
        resp.raise_for_status()
        articles = resp.json().get("articles", [])

        publishers = Counter(a["source"]["name"] for a in articles if a.get("source"))
        print(f"\n{query!r} — {len(articles)} articles, {len(publishers)} distinct publishers:")
        for name, count in publishers.most_common(20):
            print(f"  {count:3d}  {name}")


if __name__ == "__main__":
    run()