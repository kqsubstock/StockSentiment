"""
rollup_exports.py — Consolidates a day's worth of per-run StockTwits
CSV exports into a single dated file, then removes the originals.

Only rolls up dates strictly before today, so a day still receiving
new pipeline runs is never merged prematurely. Safe to re-run — if a
day's rollup file already exists, that date is skipped rather than
merged again.
"""
import csv
import re
from pathlib import Path
from datetime import datetime, timezone

EXPORT_DIR = Path(__file__).parent.parent / "data" / "exports"
FILENAME_PATTERN = re.compile(r"^stocktwits_(\d{8})_\d{6}\.csv$")
FIELDNAMES = ["ticker", "source", "source_message_id", "timestamp",
              "raw_text", "sentiment_score", "label", "scored_by"]


def group_files_by_date(export_dir):
    """Scans for per-run CSVs and groups their paths by the date
    portion of the filename. Already-rolled-up files (suffix
    '_rollup' instead of a time) won't match the pattern, so they're
    naturally excluded from being re-merged."""
    groups = {}
    for path in export_dir.glob("stocktwits_*.csv"):
        match = FILENAME_PATTERN.match(path.name)
        if not match:
            continue
        date_str = match.group(1)
        groups.setdefault(date_str, []).append(path)
    return groups


def rollup_date(export_dir, date_str, run_paths):
    """Merges all run CSVs for one date into a single file, then
    deletes the originals — only after the merged file is fully
    written, so a failure mid-write can't lose data."""
    rollup_path = export_dir / f"stocktwits_{date_str}_rollup.csv"
    if rollup_path.exists():
        print(f"  {date_str}: rollup already exists, skipping")
        return

    all_rows = []
    for path in sorted(run_paths):  # chronological order within the day
        with open(path, newline="", encoding="utf-8") as f:
            all_rows.extend(csv.DictReader(f))

    with open(rollup_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(all_rows)

    for path in run_paths:
        path.unlink()

    print(f"  {date_str}: merged {len(run_paths)} files "
          f"({len(all_rows)} rows) -> {rollup_path.name}")


def run():
    if not EXPORT_DIR.exists():
        raise FileNotFoundError(f"No exports directory at {EXPORT_DIR.resolve()}")

    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    groups = group_files_by_date(EXPORT_DIR)
    past_dates = {d: paths for d, paths in groups.items() if d < today_str}

    if not past_dates:
        print("No past-date export files to roll up.")
        return

    print(f"Rolling up {len(past_dates)} past date(s)...\n")
    for date_str in sorted(past_dates):
        rollup_date(EXPORT_DIR, date_str, past_dates[date_str])


if __name__ == "__main__":
    run()