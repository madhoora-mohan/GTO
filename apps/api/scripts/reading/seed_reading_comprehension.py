"""
Step 4.1 — Seed reading_passages and reading_questions into Neon, with
content bodies (passage text, furigana, translation, question text/options/
answer/explanation) written to R2 under the same content-offload pattern as
the existing `files` table.

Run from apps/api/ (after all Track A/B generation scripts have produced
their track_a_*.json / track_b_*.json files):

    uv run scripts/reading/seed_reading_comprehension.py

Why insert-then-update for content_key rather than computing the key
upfront: the R2 object key includes the auto-generated Neon `id`, which
doesn't exist until after the INSERT. This two-step pattern (insert row,
get id, write R2 object, update row with the key) is intentional.
"""

import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# Running this script directly (`uv run python scripts/reading/...py`) puts
# only the script's own directory on sys.path, not the apps/api/ root where
# the `app` package lives. Add the current working directory (apps/api/,
# assuming that's where this is run from) so `app.services.r2_service` —
# the existing R2 client we're told to reuse rather than duplicate — is
# importable.
sys.path.insert(0, os.getcwd())

from app.services.r2_service import put_json  # noqa: E402

load_dotenv()
DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

RAW_DIR = Path("data/raw/reading")

SEED_FILES = [
    "track_a_jaquad.json",
    "track_a_jsquad.json",
    "track_a_aozora.json",
    "track_b_n5.json",
    "track_b_n4.json",
    "track_b_n3.json",
]


def seed_passage(conn, passage: dict) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO reading_passages
            (title, jlpt_level, difficulty_score, word_count, source, content_key)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            passage.get("title"),
            passage["jlpt_level"],
            passage["difficulty_score"],
            passage["word_count"],
            passage["source"],
            "PLACEHOLDER",
        ),
    )
    passage_id = cur.fetchone()[0]

    content_key = f"reading/passages/{passage_id}.json"
    put_json(content_key, {
        "passage_text": passage["passage_text"],
        "furigana_segments": passage.get("furigana_segments"),
        "english_translation": passage.get("english_translation"),
    })

    cur.execute(
        "UPDATE reading_passages SET content_key = %s WHERE id = %s",
        (content_key, passage_id),
    )
    conn.commit()
    return passage_id


def seed_questions(conn, passage_id: int, questions: list[dict]) -> None:
    cur = conn.cursor()
    for order, q in enumerate(questions, start=1):
        cur.execute(
            """
            INSERT INTO reading_questions (passage_id, question_order, content_key)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (passage_id, order, "PLACEHOLDER"),
        )
        question_id = cur.fetchone()[0]

        content_key = f"reading/questions/{question_id}.json"
        put_json(content_key, {
            "question_text": q["question_text"],
            "options": q["options"],
            "correct_answer": q["correct_answer"],
            "explanation": q["explanation"],
        })

        cur.execute(
            "UPDATE reading_questions SET content_key = %s WHERE id = %s",
            (content_key, question_id),
        )
    conn.commit()


def seed_from_file(conn, filepath: Path) -> int:
    with open(filepath, encoding="utf-8") as f:
        items = json.load(f)
    print(f"Seeding {len(items)} passages from {filepath.name}...")
    for item in items:
        passage_id = seed_passage(conn, item)
        seed_questions(conn, passage_id, item["questions"])
    print(f"  Done: {len(items)} passages seeded from {filepath.name}.")
    return len(items)


def main() -> None:
    total = 0
    with psycopg.connect(DB_URL) as conn:
        for filename in SEED_FILES:
            filepath = RAW_DIR / filename
            if not filepath.exists():
                print(f"  [SKIP] {filename} not found")
                continue
            total += seed_from_file(conn, filepath)
    print(f"\nTotal passages seeded: {total}")


if __name__ == "__main__":
    main()
