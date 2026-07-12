"""
run_pipeline.py — Daily batch wrapper. Runs the full pipeline in the
correct dependency order:

    1. stocktwits_scraper.py (scrapers/) — pull new posts
    2. compute_week_relative.py — link records to earnings events + week
    3. finbert_vader_scorer.py  — score unlabeled rows
    4. relevance_flagger.py     — flag unflagged rows
    5. build_confidence_trajectory.py — extend Bayesian trajectories
    6. resolve_signal.py        — resolve per-event signal at week -2
    7. resolve_earnings_outcomes.py — fills in actual_outcome + actual_move_pct once each event's reaction window has passed
    8. pull_iv_history.py       — snapshot ATM IV per ticker for IV rank history

Each step runs independently — a failure is logged and the pipeline
continues to the next step rather than aborting. Since every
downstream script only processes NULL/unflagged/new rows, a partial
failure just means less gets processed until the next successful
run — nothing gets corrupted or double-counted by continuing.

Intended to be triggered once daily by Windows Task Scheduler.
Exits with a non-zero code if any step failed, so Task Scheduler's
"last run result" reflects it.
"""
import importlib
import sys
import traceback
from datetime import datetime
from pathlib import Path

# scrapers/ is a sibling of db/, not inside it — needs to be added
# explicitly since Python only auto-adds this script's own folder.
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scrapers"))

STEPS = [
    # ("scrape", "stocktwits_scraper"),   -- scraper now runs on its own Task Scheduler job (every 2h), not as part of this daily pipeline
    ("link weeks", "compute_week_relative"),
    ("flag relevance", "relevance_flagger"),      # moved up
    ("score sentiment", "finbert_vader_scorer"),  # moved down
    ("build trajectories", "build_confidence_trajectory"),
    ("resolve signals", "resolve_signal"),
    ("resolve outcomes", "resolve_earnings_outcomes"),
    ("pull IV history", "pull_iv_history"),
]


def run():
    start_time = datetime.now()
    print(f"\n{'='*70}\nPipeline run started: {start_time.isoformat()}\n{'='*70}")
    results = []

    for label, module_name in STEPS:
        print(f"\n--- {label} ({module_name}.py) ---")
        try:
            module = importlib.import_module(module_name)
            module.run()
            results.append((label, "OK"))
        except Exception:
            print(f"FAILED: {label}")
            traceback.print_exc()
            results.append((label, "FAILED"))

    print(f"\n{'='*70}\nPipeline summary:")
    for label, status in results:
        print(f"  [{status:6s}] {label}")
    print(f"{'='*70}\n")

    end_time = datetime.now()
    duration = end_time - start_time
    print(f"\n{'='*70}\nPipeline runtime: {duration}\n{'='*70}")

    if any(status == "FAILED" for _, status in results):
        sys.exit(1)


if __name__ == "__main__":
    run()