"""
verify_neutral_spike.py — one-time diagnostic, safe to delete after running.

Read-only. Checks whether the [0.0, 0.2) spike in sentiment_score is
driven by FinBERT's neutral-label rows (where finbert_raw is forced to
exactly 0.0, per the fb_map in finbert_vader_scorer.py) dominating the
blend via VADER's near-zero default, rather than reflecting genuinely
neutral sentiment.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT finbert_raw, vader_raw, sentiment_score
        FROM sentiment_records
        WHERE scored_by = 'finbert_vader_hybrid'
        """
    )
    rows = cur.fetchall()
    conn.close()

    zero_fb = [(fb, v, s) for fb, v, s in rows if fb == 0.0]
    nonzero_fb = [(fb, v, s) for fb, v, s in rows if fb != 0.0]

    zero_fb_in_spike = sum(1 for _, _, s in zero_fb if 0.0 <= s < 0.2)
    nonzero_fb_in_spike = sum(1 for _, _, s in nonzero_fb if 0.0 <= s < 0.2)

    total_spike = zero_fb_in_spike + nonzero_fb_in_spike

    print(f"Total finbert_vader_hybrid rows: {len(rows)}")
    print(f"Rows where finbert_raw == 0.0 (FinBERT called neutral): {len(zero_fb)}")
    print(f"Rows where finbert_raw != 0.0: {len(nonzero_fb)}")

    print(f"\n[0.0, 0.2) spike bucket total: {total_spike}")
    print(f"  From finbert_raw == 0.0 rows:  {zero_fb_in_spike}  "
          f"({zero_fb_in_spike/total_spike*100:.1f}% of spike)" if total_spike else "")
    print(f"  From finbert_raw != 0.0 rows:  {nonzero_fb_in_spike}  "
          f"({nonzero_fb_in_spike/total_spike*100:.1f}% of spike)" if total_spike else "")

    if zero_fb:
        vader_vals = [v for _, v, _ in zero_fb]
        print(f"\nFor finbert_raw == 0.0 rows — vader_raw stats:")
        print(f"  min:  {min(vader_vals):.4f}")
        print(f"  max:  {max(vader_vals):.4f}")
        print(f"  avg:  {sum(vader_vals)/len(vader_vals):.4f}")


if __name__ == "__main__":
    run()