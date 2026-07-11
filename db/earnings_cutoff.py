"""
earnings_cutoff.py — Shared cutoff-date logic used by compute_week_relative.py
and resolve_earnings_outcomes.py, so both scripts agree on when "the market
knew" about an earnings report.

Cutoff logic:
  - AMC:            cutoff = midnight Eastern the day AFTER earnings_date
                     (the whole earnings day is still "pre-reaction")
  - BMO / unknown:  cutoff = midnight Eastern OF earnings_date
                     (conservative fail-safe — treat unknown as BMO)
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")


def compute_cutoff_utc(earnings_date_str, report_time):
    """
    earnings_date_str: 'YYYY-MM-DD'
    report_time: 'BMO' | 'AMC' | 'unknown'
    Returns the UTC datetime marking the boundary between "pre-earnings"
    and "post-earnings."
    """
    event_date = datetime.strptime(earnings_date_str, "%Y-%m-%d").date()

    if report_time == "AMC":
        cutoff_date = event_date + timedelta(days=1)
    else:  # 'BMO' or 'unknown' — conservative fail-safe
        cutoff_date = event_date

    cutoff_eastern = datetime(
        cutoff_date.year, cutoff_date.month, cutoff_date.day,
        0, 0, 0, tzinfo=EASTERN,
    )
    return cutoff_eastern.astimezone(timezone.utc)