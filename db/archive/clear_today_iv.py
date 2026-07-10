"""
clear_today_iv.py — One-time throwaway cleanup script.
Clears today's iv_history rows so pull_iv_history.py can be re-run cleanly.
Safe to delete after running.
"""
import sqlite3
from pathlib import Path
from datetime import date

DB_PATH = Path(__file__).parent.parent.parent / "data" / "pipeline.db"

conn = sqlite3.connect(DB_PATH)
today_str = date.today().isoformat()
cur = conn.execute("DELETE FROM iv_history WHERE date = ?", (today_str,))
conn.commit()
print(f"Cleared {cur.rowcount} rows for {today_str}")
conn.close()