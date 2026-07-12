"""
finbert_vader_scorer.py — Scores unlabeled sentiment_records rows using
a FinBERT + VADER hybrid (0.6 FinBERT / 0.4 VADER weighted average).

Only processes rows where label IS NULL — StockTwits-tagged rows are
never touched, since that crowd label is itself valuable training data.

Safe to re-run: idempotent, only ever targets label IS NULL rows, so
running it again after a fresh scrape just picks up the new untagged rows.

FinBERT score extraction (updated): previously used only the top label
via a fixed {"positive": 1, "negative": -1, "neutral": 0} mapping, which
discarded FinBERT's confidence entirely whenever "neutral" won — forcing
finbert_raw to exactly 0.0 for ~71% of rows and letting VADER's near-zero
default decide those rows almost alone. Now pulls all three class
probabilities (via top_k=None) and computes positive_prob - negative_prob,
so even neutral-labeled rows carry a real, continuous signal instead of
a hard zero.
"""
import re
import sqlite3
from pathlib import Path

from transformers import pipeline
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"

FINBERT_WEIGHT = 0.6
VADER_WEIGHT = 0.4
BULLISH_THRESHOLD = 0.3
BEARISH_THRESHOLD = -0.3
DISAGREEMENT_THRESHOLD = 1.0


finbert = pipeline("sentiment-analysis", model="ProsusAI/finbert", top_k=None)
vader = SentimentIntensityAnalyzer()


def clean_for_finbert(text):
    """FinBERT wasn't trained on cashtags/URLs/HTML entities — strip them
    so the model isn't wasting attention on tokens it doesn't understand."""
    text = re.sub(r"\$[A-Z]{1,5}\b", "", text)   # cashtags: $AAPL, $NVDA
    text = re.sub(r"http\S+", "", text)           # URLs
    text = re.sub(r"&#\d+;", "", text)             # HTML entities: &#39;
    return text.strip()


# VADER gets raw_text unchanged, no cleaning function needed —
# its lexicon treats caps, punctuation ("!!!"), and emoji as signal,
# so stripping them would throw away information VADER relies on.


DANGER_WORDS = ["crush", "crushed", "crushing", "beat", "beats", "beating", "beaten"]

def check_idiom_flag(raw_text):
    text_lower = raw_text.lower()
    return int(any(re.search(rf"\b{w}\b", text_lower) for w in DANGER_WORDS))


def score_record(raw_text):
    finbert_input = clean_for_finbert(raw_text)

    # top_k=None returns all class scores: a list of dicts, one per label,
    # wrapped in an outer list (one entry per input text — we only pass one).
    fb_results = finbert(finbert_input[:512])[0]  # truncate — FinBERT's token limit
    scores_by_label = {r["label"]: r["score"] for r in fb_results}

    # Continuous score from all three probabilities, not just the top label.
    # A confident neutral call now yields a value near 0 because positive_prob
    # and negative_prob are both genuinely low — not because we threw them away.
    finbert_score = scores_by_label["positive"] - scores_by_label["negative"]

    vader_score = vader.polarity_scores(raw_text)["compound"]

    final_score = FINBERT_WEIGHT * finbert_score + VADER_WEIGHT * vader_score

    if final_score > BULLISH_THRESHOLD:
        label = "bullish"
    elif final_score < BEARISH_THRESHOLD:
        label = "bearish"
    else:
        label = "neutral"

    idiom_flag = check_idiom_flag(raw_text)

    disagreement_flag = int(abs(finbert_score - vader_score) > DISAGREEMENT_THRESHOLD)

    return finbert_score, vader_score, final_score, label, idiom_flag, disagreement_flag


def get_unlabeled_records(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, raw_text FROM sentiment_records
        WHERE label IS NULL
          AND (relevance_flag IS NULL OR relevance_flag = 0)
        """
    )
    return cur.fetchall()


def run():
    conn = sqlite3.connect(DB_PATH)
    records = get_unlabeled_records(conn)
    print(f"Scoring {len(records)} unlabeled records...\n")

    cur = conn.cursor()
    flagged_count = 0
    disagreement_count = 0

    for record_id, raw_text in records:
        finbert_score, vader_score, final_score, label, idiom_flag, disagreement_flag = score_record(raw_text)

        if idiom_flag:
            flagged_count += 1
        if disagreement_flag:
            disagreement_count += 1

        cur.execute(
            """UPDATE sentiment_records
               SET sentiment_score = ?, finbert_raw = ?, vader_raw = ?,
                   label = ?, idiom_flag = ?, disagreement_flag = ?, scored_by = ?
               WHERE id = ?""",
            (final_score, finbert_score, vader_score, label, idiom_flag,
             disagreement_flag, "finbert_vader_hybrid", record_id)
        )

    conn.commit()
    print(f"Scored {len(records)} records. {flagged_count} flagged for idiom risk, "
          f"{disagreement_count} flagged for model disagreement.")

    cur.execute(
        """SELECT label, COUNT(*) FROM sentiment_records
           WHERE scored_by = 'finbert_vader_hybrid'
           GROUP BY label"""
    )
    print("\nLabel distribution (this run):")
    for label, count in cur.fetchall():
        print(f"  {label:10s} {count}")

    conn.close()


if __name__ == "__main__":
    run()