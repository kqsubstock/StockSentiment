import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute(
    """
    SELECT ticker, COUNT(*)
    FROM sentiment_records
    WHERE week_relative = -4
    GROUP BY ticker
    ORDER BY COUNT(*) DESC
    """
)
for ticker, count in cur.fetchall():
    print(f"  {ticker:6s} {count}")

conn.close()