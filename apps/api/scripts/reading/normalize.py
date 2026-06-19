"""
Step 2.3 — Load + clean up JaQuAD/JSQuAD raw data into a flat intermediate
format that score_passages.py and the question-generation step can consume.

Run from apps/api/ (after download_sources.py has populated
data/raw/reading/jaquad/ and data/raw/reading/jsquad/):

    uv run scripts/reading/normalize.py

Why normalization is needed at all:
Both JaQuAD and JSQuAD are built from Wikipedia articles, and Wikipedia
source text carries artifacts that don't belong in a clean reading passage:
numbered reference markers like "[1]", leftover HTML entities like "&amp;",
and "== Section Header ==" style markup. normalize_jaquad_jsquad() strips
those out. JSQuAD additionally prefixes every `context` with
"{title} [SEP] " (its own internal format) — we strip that prefix too.

What this script outputs:
data/raw/reading/normalized_jaquad.json and normalized_jsquad.json — each
a flat list of:
    {"source": "jaquad"|"jsquad", "title": str, "passage_text": str,
     "qas": [{"question": str, "answer_text": str}, ...]}

One entry per *paragraph* (JaQuAD) or per unique *context* (JSQuAD) — not
per individual question, even though each paragraph/context usually has
several QA pairs attached to it. We keep all of a paragraph's QA pairs
together because Step 2.6 will pick ONE to turn into an MCQ (or generate
more) for that passage, and a passage should appear at most once in our
final passage list.
"""

import json
import re
import unicodedata
from pathlib import Path

from datasets import load_from_disk

RAW_DIR = Path("data/raw/reading")

# Reasonable bounds for a single reading-comprehension passage. Wikipedia
# paragraphs vary wildly in length — a one-sentence paragraph isn't a
# passage, and a 5000-character paragraph is a full article section, not a
# single passage a learner reads in one sitting. These bounds are a judgment
# call (the handoff doc doesn't specify one for Track A — it only gives a
# 300-800 *word* target for Aozora); chosen to keep N2/N1 passages roughly
# comparable in size to what Track B generates for N3 (120-200 characters)
# scaled up for harder levels.
MIN_PASSAGE_CHARS = 150
MAX_PASSAGE_CHARS = 1000


def normalize_jaquad_jsquad(text: str) -> str:
    """Wikipedia-sourced text: strip reference markers, HTML entities, headers."""
    text = re.sub(r"\[\d+\]", "", text)          # [1], [23] reference markers
    text = re.sub(r"&[a-z]+;", "", text)          # &amp; etc.
    text = re.sub(r"^=+.*=+$", "", text, flags=re.MULTILINE)  # == headers ==
    text = unicodedata.normalize("NFKC", text)
    return text.strip()


def load_jaquad() -> list[dict]:
    """Read every jaquad_*.json shard, group qas by (title, context) so each
    paragraph appears once with all its questions attached."""
    entries: list[dict] = []
    jaquad_dir = RAW_DIR / "jaquad"
    for shard_path in sorted(jaquad_dir.glob("*.json")):
        with open(shard_path, encoding="utf-8") as f:
            shard = json.load(f)
        for article in shard["data"]:
            title = article["title"]
            for paragraph in article["paragraphs"]:
                passage_text = normalize_jaquad_jsquad(paragraph["context"])
                qas = [
                    {"question": qa["question"], "answer_text": qa["answers"][0]["text"]}
                    for qa in paragraph["qas"]
                    if qa.get("answers")
                ]
                if not qas:
                    continue
                entries.append({
                    "source": "jaquad",
                    "title": title,
                    "passage_text": passage_text,
                    "qas": qas,
                })
    return entries


def load_jsquad() -> list[dict]:
    """JSQuAD is one row per question, with the same context repeated
    across rows. Group rows by raw context so each paragraph appears once."""
    ds = load_from_disk(str(RAW_DIR / "jsquad"))

    by_context: dict[str, dict] = {}
    for split in ("train", "validation"):
        for row in ds[split]:
            if row.get("is_impossible"):
                continue
            raw_context = row["context"]
            # JSQuAD format: "{title} [SEP] {actual context}"
            context = raw_context.split("[SEP]", 1)[-1].strip()
            if context not in by_context:
                by_context[context] = {
                    "source": "jsquad",
                    "title": row["title"],
                    "passage_text": normalize_jaquad_jsquad(context),
                    "qas": [],
                }
            answers = row["answers"]["text"]
            if answers:
                by_context[context]["qas"].append({
                    "question": row["question"],
                    "answer_text": answers[0],
                })

    return [entry for entry in by_context.values() if entry["qas"]]


def filter_by_length(entries: list[dict]) -> list[dict]:
    return [
        e for e in entries
        if MIN_PASSAGE_CHARS <= len(e["passage_text"]) <= MAX_PASSAGE_CHARS
    ]


def main() -> None:
    print("Loading + normalizing JaQuAD...")
    jaquad = filter_by_length(load_jaquad())
    print(f"  {len(jaquad)} passages in [{MIN_PASSAGE_CHARS}, {MAX_PASSAGE_CHARS}] char range")

    print("Loading + normalizing JSQuAD...")
    jsquad = filter_by_length(load_jsquad())
    print(f"  {len(jsquad)} passages in [{MIN_PASSAGE_CHARS}, {MAX_PASSAGE_CHARS}] char range")

    with open(RAW_DIR / "normalized_jaquad.json", "w", encoding="utf-8") as f:
        json.dump(jaquad, f, ensure_ascii=False, indent=2)
    with open(RAW_DIR / "normalized_jsquad.json", "w", encoding="utf-8") as f:
        json.dump(jsquad, f, ensure_ascii=False, indent=2)

    print(f"\nWritten to {RAW_DIR}/normalized_jaquad.json and normalized_jsquad.json")


if __name__ == "__main__":
    main()
