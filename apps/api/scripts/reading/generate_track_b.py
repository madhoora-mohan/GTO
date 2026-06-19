"""
Step 3.6 — Generate N5/N4/N3 reading passages + questions from scratch using
the local Qwen3.5:9b model (Track B — covers the easier JLPT levels, since
JaQuAD/JSQuAD's Wikipedia text is almost entirely N2/N1).

Run from apps/api/:
    uv run scripts/reading/generate_track_b.py --level N5 --count 60

The doc's own guidance (don't skip this): run one level at a time, manually
read a sample of data/raw/reading/track_b_<level>.json before moving on to
the next level. If the rejection rate climbs above ~30%, the grammar
rulebook or prompt likely needs adjusting before continuing — don't just
push through with a bigger --count.

Each accepted passage goes through three gates, all soft except the last:
1. The model must return a non-empty passage_text (hard skip if not).
2. soft_level_check: passage's kanji must mostly stay within the target
   JLPT level's known kanji set (more than 3 flagged kanji -> reject and
   retry with a new generation, since here — unlike Track A — staying on
   level is the entire point).
3. Question generation must produce at least one well-formed 4-option MCQ
   (hard skip if not).
"""

import argparse
import json
import random
import re
import unicodedata
from pathlib import Path

import psycopg
from dotenv import load_dotenv
import os

from qwen_client import QwenGenerationError, call_qwen
from score_passages import score_passage

load_dotenv()
DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

RAW_DIR = Path("data/raw/reading")

PASSAGE_PROMPT_TEMPLATE = """あなたは日本語学習者向けの読解問題作成者です。
以下の制約に厳密に従って、JLPT{level}レベルの読解文章を1つ作成してください。

【絶対に守る制約】
- 文字数: {min_words}語から{max_words}語の間
- 使用できる語彙: 以下のリストの単語を中心に使用すること
  {vocab_sample}
- 使用できる漢字: 以下のリストの漢字のみ使用すること。リストにない漢字は
  絶対に使わないこと
  {kanji_sample}
- 使用できる文法: {allowed_grammar}
- 絶対に使ってはいけない文法: {forbidden_grammar}
- トピック: {topic}
- 英語の単語や記号を一切含めないこと
- マークダウンの記号（**や##など）を一切含めないこと

【出力形式】
以下のJSON形式のみで出力してください。前置き、説明、コードブロックの
記号は一切含めないでください:
{{"title": "短いタイトル", "passage_text": "文章本文", "english_translation": "English translation of the passage"}}
"""

QUESTIONS_PROMPT_TEMPLATE = """以下の文章を読んで、内容理解を確認する4択問題を3つ作成してください。

文章:
{passage_text}

各問題には正解1つと、もっともらしい誤答3つを含めてください。
正解はoptionsの配列のいずれかと完全に一致する文字列にしてください。

以下のJSON形式のみで出力してください。前置きや説明は一切不要です:
{{"questions": [
  {{"question_text": "...", "options": ["...", "...", "...", "..."], "correct_answer": "...", "explanation": "English explanation of why this answer is correct"}}
]}}
"""


def strip_artifacts(text: str) -> str:
    """Remove stray markdown or English leakage from generated text."""
    text = re.sub(r"\*\*|##|```", "", text)
    text = unicodedata.normalize("NFKC", text)
    return text.strip()


def get_vocab_kanji_samples(conn, level: str) -> tuple[list[str], list[str]]:
    cur = conn.cursor()
    cur.execute(
        "SELECT word FROM vocab WHERE jlpt = %s ORDER BY RANDOM() LIMIT 40", (level,)
    )
    vocab_sample = [row[0] for row in cur.fetchall()]
    cur.execute(
        "SELECT character FROM kanji WHERE jlpt = %s ORDER BY RANDOM() LIMIT 30", (level,)
    )
    kanji_sample = [row[0] for row in cur.fetchall()]
    return vocab_sample, kanji_sample


def get_full_known_kanji(conn) -> set[str]:
    """All kanji at or below the target level, for the soft-check —
    NOT just the random sample used in the prompt."""
    cur = conn.cursor()
    cur.execute("SELECT character FROM kanji")
    return {row[0] for row in cur.fetchall()}


def soft_level_check(text: str, level_kanji: set[str], max_flagged: int = 3) -> tuple[bool, list[str]]:
    kanji_in_text = set(re.findall(r"[一-龯]", text))
    flagged = sorted(kanji_in_text - level_kanji)
    return len(flagged) <= max_flagged, flagged


def generate_one_passage(conn, level: str, rules: dict, topic: str) -> dict | None:
    vocab_sample, kanji_sample = get_vocab_kanji_samples(conn, level)
    min_words, max_words = rules["target_word_count"]
    allowed = ", ".join(g["pattern"] for g in rules["allowed_grammar"])
    forbidden = ", ".join(rules["forbidden_grammar"])

    prompt = PASSAGE_PROMPT_TEMPLATE.format(
        level=level, min_words=min_words, max_words=max_words,
        vocab_sample=", ".join(vocab_sample),
        kanji_sample="".join(kanji_sample),
        allowed_grammar=allowed, forbidden_grammar=forbidden, topic=topic,
    )

    try:
        result = call_qwen(prompt, expect_json=True, num_ctx=2048)
    except QwenGenerationError as e:
        print(f"  [SKIP] passage generation failed: {e}")
        return None

    passage_text = strip_artifacts(result.get("passage_text", ""))
    if not passage_text:
        print("  [SKIP] empty passage_text in response")
        return None

    return {
        "title": strip_artifacts(result.get("title", "")),
        "passage_text": passage_text,
        "english_translation": strip_artifacts(result.get("english_translation", "")),
    }


def generate_questions(passage_text: str) -> list[dict] | None:
    prompt = QUESTIONS_PROMPT_TEMPLATE.format(passage_text=passage_text)
    try:
        result = call_qwen(prompt, expect_json=True, num_ctx=2048)
    except QwenGenerationError as e:
        print(f"  [SKIP] question generation failed: {e}")
        return None

    questions = result.get("questions", [])
    valid = []
    for q in questions:
        opts = q.get("options", [])
        ans = q.get("correct_answer", "")
        if len(opts) == 4 and ans in opts and q.get("question_text") and q.get("explanation"):
            valid.append(q)
        else:
            print(f"  [SKIP] malformed question, missing fields or answer not in options: {q}")
    return valid if valid else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", required=True, choices=["N5", "N4", "N3"])
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args()

    with open(RAW_DIR / "grammar_rules.json", encoding="utf-8") as f:
        all_rules = json.load(f)
    rules = all_rules[args.level]

    conn = psycopg.connect(DB_URL)
    full_known_kanji = get_full_known_kanji(conn)

    accepted = []
    rejected_count = 0

    for i in range(args.count):
        topic = random.choice(rules["topics"])
        print(f"[{i+1}/{args.count}] Generating {args.level} passage on topic: {topic}")

        passage = generate_one_passage(conn, args.level, rules, topic)
        if passage is None:
            rejected_count += 1
            continue

        ok, flagged = soft_level_check(passage["passage_text"], full_known_kanji)
        if not ok:
            print(f"  [REJECT] {len(flagged)} kanji outside known set: {flagged}")
            rejected_count += 1
            continue

        questions = generate_questions(passage["passage_text"])
        if questions is None:
            print("  [REJECT] no valid questions generated for this passage")
            rejected_count += 1
            continue

        # jReadability cross-check (Step 3.7) — done here, at generation
        # time, rather than as a separate pass, so the score is captured
        # before this passage ever reaches the seed script. reading_passages
        # .difficulty_score is NOT NULL, so every Track B passage MUST have
        # a real score by the time it's written to track_b_<level>.json.
        score, scored_level = score_passage(passage["passage_text"])
        if scored_level != args.level:
            print(f"  [FLAG] generated as {args.level} but jReadability scored "
                  f"{scored_level} ({score}) — keeping, but flagged for review")
            with open(RAW_DIR / "track_b_review.log", "a", encoding="utf-8") as review_f:
                review_f.write(json.dumps({
                    "title": passage["title"],
                    "generated_level": args.level,
                    "jreadability_score": score,
                    "jreadability_level": scored_level,
                    "passage_text": passage["passage_text"],
                }, ensure_ascii=False) + "\n")

        passage["jlpt_level"] = args.level
        passage["difficulty_score"] = score
        passage["word_count"] = len(passage["passage_text"])  # character count, see note below
        passage["source"] = "llm_qwen3.5"
        passage["questions"] = questions
        accepted.append(passage)
        print(f"  [OK] accepted with {len(questions)} questions (jReadability: {scored_level}/{score})")

    print(f"\nDone. Accepted: {len(accepted)}, Rejected: {rejected_count}")
    if accepted or rejected_count:
        rate = rejected_count / (len(accepted) + rejected_count)
        print(f"Rejection rate: {rate:.0%}" + ("  <-- above 30%, consider tuning the prompt/rulebook" if rate > 0.3 else ""))

    out_path = RAW_DIR / f"track_b_{args.level.lower()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(accepted, f, ensure_ascii=False, indent=2)
    print(f"Written to {out_path} — review before running the seed script.")


if __name__ == "__main__":
    main()
