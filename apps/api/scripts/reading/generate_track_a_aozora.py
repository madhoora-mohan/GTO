"""
Step 2.4 + 2.5 + 2.6 (Aozora half) — Score, soft-check, and generate
questions from scratch for the 30-50 manually-curated Aozora works.

Run from apps/api/ (after normalize_aozora.py has produced
data/raw/reading/normalized_aozora.json):

    uv run scripts/reading/generate_track_a_aozora.py

Unlike JaQuAD/JSQuAD, Aozora passages come with NO existing question at
all — there's no extractive Q&A dataset behind classic literature. So
instead of the distractor-only prompt used for JaQuAD/JSQuAD,
AOZORA_QUESTION_PROMPT_TEMPLATE asks Qwen3.5:9b to invent 3 full
comprehension questions (with their own 4-option MCQs) from scratch, given
just the passage text. Same call_qwen() helper, same think:false
discipline — no second calling convention for this.

furigana_segments ARE kept here (unlike Track A's other two sources) —
these come from Aozora's own human-verified ruby markup, which is exactly
the case the furigana_segments column was designed for.
"""

import json
from pathlib import Path

from qwen_client import QwenGenerationError, call_qwen
from score_passages import score_passage

RAW_DIR = Path("data/raw/reading")
FLAGS_LOG = RAW_DIR / "track_a_flags.log"

AOZORA_QUESTION_PROMPT_TEMPLATE = """あなたは日本語読解問題の作成者です。
以下の文章を読んで、内容理解を確認する4択問題を3つ作成してください。

文章:
{plain_text}

各問題には正解1つと、もっともらしい誤答3つを含めてください。

以下のJSON形式のみで出力してください。説明や前置きは一切不要です:
{{"questions": [
  {{"question_text": "...", "options": ["...", "...", "...", "..."], "correct_answer": "...", "explanation": "English explanation"}},
  ...
]}}
"""


def generate_aozora_questions(passage_text: str) -> list[dict] | None:
    # Aozora stories run long — our curated selection's longest entry
    # (10444 chars) measured at 6548 tokens via Ollama's prompt_eval_count,
    # confirmed empirically before this was set (not guessed): num_ctx=4096
    # (Track A's other default) would silently truncate it, and 8192 was
    # measured to cost only ~240MB extra VRAM, comfortably within headroom.
    prompt = AOZORA_QUESTION_PROMPT_TEMPLATE.format(plain_text=passage_text)
    try:
        result = call_qwen(prompt, expect_json=True, num_ctx=8192)
    except QwenGenerationError as e:
        print(f"    [SKIP] question generation failed: {e}")
        return None

    questions = result.get("questions", [])
    valid = []
    for q in questions:
        opts = q.get("options", [])
        ans = q.get("correct_answer", "")
        if len(opts) == 4 and ans in opts and q.get("question_text") and q.get("explanation"):
            valid.append(q)
        else:
            print(f"    [SKIP] malformed question: {q}")
    return valid if valid else None


def main() -> None:
    with open(RAW_DIR / "normalized_aozora.json", encoding="utf-8") as f:
        candidates = json.load(f)

    accepted = []
    rejected_count = 0
    level_counts: dict[str, int] = {}

    with open(FLAGS_LOG, "a", encoding="utf-8") as flags_f:
        for i, candidate in enumerate(candidates):
            passage_text = candidate["passage_text"]
            score, level = score_passage(passage_text)
            level_counts[level] = level_counts.get(level, 0) + 1
            print(f"[{i+1}/{len(candidates)}] {candidate['title']} "
                  f"({level}, score={score}, {len(passage_text)} chars)")

            # Soft check is log-only for Track A (see soft_checks.py) — but
            # Aozora is pre-modern/early-modern literary text, which uses
            # vocabulary far outside any JLPT list far more often than
            # Wikipedia does, so flagging every passage here would be
            # noise. We log the score/level only, not kanji/vocab flags,
            # for Aozora specifically.
            flags_f.write(json.dumps({
                "source": "aozora", "title": candidate["title"],
                "score": score, "level": level,
            }, ensure_ascii=False) + "\n")

            questions = generate_aozora_questions(passage_text)
            if questions is None:
                rejected_count += 1
                continue

            accepted.append({
                "title": candidate["title"],
                "passage_text": passage_text,
                "jlpt_level": level,
                "difficulty_score": score,
                "word_count": len(passage_text),
                "source": "aozora",
                "furigana_segments": candidate["furigana_segments"],
                "english_translation": None,
                "questions": questions,
            })
            print(f"  [OK] accepted with {len(questions)} question(s)")

    print(f"\nDone. Accepted: {len(accepted)}, Rejected: {rejected_count}")
    print(f"Level distribution: {level_counts}")

    out_path = RAW_DIR / "track_a_aozora.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(accepted, f, ensure_ascii=False, indent=2)
    print(f"Written to {out_path} — review before running the seed script.")


if __name__ == "__main__":
    main()
