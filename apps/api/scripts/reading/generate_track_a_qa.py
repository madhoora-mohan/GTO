"""
Step 2.4 + 2.5 + 2.6 — Score, soft-check, sample, and turn JaQuAD/JSQuAD
normalized passages into seed-ready reading passages with MCQ questions.

Run from apps/api/ (after normalize.py has produced
data/raw/reading/normalized_{jaquad,jsquad}.json):

    uv run scripts/reading/generate_track_a_qa.py --source jaquad --count 60
    uv run scripts/reading/generate_track_a_qa.py --source jsquad --count 60

Why a --count sample instead of processing all ~10k candidates per source:
JaQuAD/JSQuAD give us a context + question + an *extractive* answer span
(a snippet copied verbatim from the text) — not a ready-made 4-option MCQ.
Turning that into a proper MCQ means asking the local Qwen3.5:9b model to
invent 3 plausible wrong answers per question, which costs one LLM call per
passage. With ~10k candidates per source, processing all of them would take
hours for marginal benefit on a personal-use app. So this script randomly
samples --count candidates (after score+soft-check filtering) per run —
re-run with a different --count, or run it again to top up, any time.

What this does NOT do: reject passages for scoring N4/N5 or for kanji/vocab
outside the known sets. Per the handoff doc (Step 2.5), Track A is
log-only — Wikipedia text legitimately uses kanji/vocab outside JLPT-tagged
lists, and our kanji table covers the full ~10,384-character KANJIDIC2 set,
so most "unknown" hits are false alarms, not real problems.
"""

import argparse
import json
import os
import random
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from qwen_client import QwenGenerationError, call_qwen
from score_passages import score_passage
from soft_checks import soft_kanji_check, soft_vocab_check

load_dotenv()
DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

RAW_DIR = Path("data/raw/reading")
FLAGS_LOG = RAW_DIR / "track_a_flags.log"

DISTRACTOR_PROMPT_TEMPLATE = """あなたは日本語読解問題の作成者です。
以下の文章と質問、正解を読んで、4択問題を作成してください。

文章: {context}
質問: {question}
正解: {correct_answer}

正解に加えて、もっともらしい誤答を3つ作成してください。誤答は文章の内容と
関連性があるが、明らかに間違っているものにしてください。

以下のJSON形式のみで出力してください。説明や前置きは一切不要です:
{{"options": ["正解", "誤答1", "誤答2", "誤答3"], "explanation": "なぜ正解が正しいかの説明（英語で1文）"}}
"""


def load_known_kanji_words(conn) -> tuple[set[str], set[str]]:
    cur = conn.cursor()
    cur.execute("SELECT character FROM kanji")
    known_kanji = {row[0] for row in cur.fetchall()}
    cur.execute("SELECT word FROM vocab")
    known_words = {row[0] for row in cur.fetchall()}
    return known_kanji, known_words


def generate_mcq(context: str, question: str, correct_answer: str) -> dict | None:
    prompt = DISTRACTOR_PROMPT_TEMPLATE.format(
        context=context, question=question, correct_answer=correct_answer
    )
    try:
        result = call_qwen(prompt, expect_json=True)
    except QwenGenerationError as e:
        print(f"    [SKIP] distractor generation failed: {e}")
        return None

    options = result.get("options", [])
    explanation = result.get("explanation", "")
    if len(options) != 4 or correct_answer not in options or not explanation:
        print(f"    [SKIP] malformed MCQ from model: {result}")
        return None

    return {
        "question_text": question,
        "options": options,
        "correct_answer": correct_answer,
        "explanation": explanation,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, choices=["jaquad", "jsquad"])
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--questions-per-passage", type=int, default=1)
    args = parser.parse_args()

    with open(RAW_DIR / f"normalized_{args.source}.json", encoding="utf-8") as f:
        candidates = json.load(f)
    random.shuffle(candidates)

    with psycopg.connect(DB_URL) as conn:
        known_kanji, known_words = load_known_kanji_words(conn)

    accepted = []
    rejected_count = 0
    level_counts: dict[str, int] = {}

    with open(FLAGS_LOG, "a", encoding="utf-8") as flags_f:
        for candidate in candidates:
            if len(accepted) >= args.count:
                break

            passage_text = candidate["passage_text"]
            score, level = score_passage(passage_text)
            level_counts[level] = level_counts.get(level, 0) + 1

            flagged_kanji = soft_kanji_check(passage_text, known_kanji)
            flagged_words = soft_vocab_check(passage_text, known_words)
            if flagged_kanji or flagged_words:
                flags_f.write(json.dumps({
                    "source": args.source,
                    "title": candidate["title"],
                    "score": score,
                    "level": level,
                    "flagged_kanji": flagged_kanji,
                    "flagged_words": flagged_words,
                }, ensure_ascii=False) + "\n")

            qas_to_use = candidate["qas"][: args.questions_per_passage]
            questions = []
            for qa in qas_to_use:
                mcq = generate_mcq(passage_text, qa["question"], qa["answer_text"])
                if mcq is not None:
                    questions.append(mcq)

            if not questions:
                rejected_count += 1
                continue

            accepted.append({
                "title": candidate["title"],
                "passage_text": passage_text,
                "jlpt_level": level,
                "difficulty_score": score,
                "word_count": len(passage_text),
                "source": args.source,
                "furigana_segments": None,
                "english_translation": None,
                "questions": questions,
            })
            print(f"[{len(accepted)}/{args.count}] accepted ({level}, score={score}) "
                  f"with {len(questions)} question(s): {candidate['title']}")

    print(f"\nDone. Accepted: {len(accepted)}, Rejected (no usable MCQ): {rejected_count}")
    print(f"Level distribution across all scanned candidates: {level_counts}")

    out_path = RAW_DIR / f"track_a_{args.source}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(accepted, f, ensure_ascii=False, indent=2)
    print(f"Written to {out_path} — review before running the seed script.")


if __name__ == "__main__":
    main()
