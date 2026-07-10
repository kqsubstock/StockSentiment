"""
reprocess_hybrid_scores.py — one-time reprocessing pass, safe to delete
after running.

Re-scores every existing finbert_vader_hybrid row using the updated
score_record() logic in finbert_vader_scorer.py (positive_prob -
negative_prob instead of a fixed top-label mapping). This is a full
re-run through FinBERT/VADER, not arithmetic backfill — finbert_raw
itself changes meaning under the new formula, so old values must be
recomputed from raw_text, not patched.

StockTwits-labeled rows (scored_by = 'stocktwits_label') are never
touched — same scope boundary as the permanent scorer.

Run this once, immediately after deploying the updated
finbert_vader_scorer.py, to bring all pre-existing rows in line with
the new formula.
"""
import sqlite3
from pathlib import Path

from finbert_vader_scorer import score_record

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"


def get_hybrid_records(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, raw_text FROM sentiment_records WHERE scored_by = 'finbert_vader_hybrid'"
    )
    return cur.fetchall()


def print_label_distribution(conn, when):
    cur = conn.cursor()
    cur.execute(
        """SELECT label, COUNT(*) FROM sentiment_records
           WHERE scored_by = 'finbert_vader_hybrid'
           GROUP BY label"""
    )
    print(f"\nLabel distribution ({when}):")
    for label, count in cur.fetchall():
        print(f"  {label:10s} {count}")


def run():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No database found at {DB_PATH.resolve()} — check the path.")

    conn = sqlite3.connect(DB_PATH)

    print_label_distribution(conn, "BEFORE reprocessing")

    records = get_hybrid_records(conn)
    print(f"\nReprocessing {len(records)} finbert_vader_hybrid rows...\n")

    cur = conn.cursor()
    flagged_count = 0
    disagreement_count = 0

    for i, (record_id, raw_text) in enumerate(records, start=1):
        finbert_score, vader_score, final_score, label, idiom_flag, disagreement_flag = score_record(raw_text)

        if idiom_flag:
            flagged_count += 1
        if disagreement_flag:
            disagreement_count += 1

        cur.execute(
            """UPDATE sentiment_records
               SET sentiment_score = ?, finbert_raw = ?, vader_raw = ?,
                   label = ?, idiom_flag = ?, disagreement_flag = ?
               WHERE id = ?""",
            (final_score, finbert_score, vader_score, label, idiom_flag,
             disagreement_flag, record_id)
        )

        if i % 50 == 0:
            print(f"  ...{i}/{len(records)} reprocessed")

    conn.commit()

    print(f"\nReprocessed {len(records)} rows.")
    print(f"{flagged_count} flagged for idiom risk, {disagreement_count} flagged for model disagreement.")

    print_label_distribution(conn, "AFTER reprocessing")

    conn.close()


if __name__ == "__main__":
    run()