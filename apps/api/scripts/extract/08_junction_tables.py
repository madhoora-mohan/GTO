"""
Step 8 — Build kanji/vocab/sentence junction tables.

Run from apps/api/:
    uv run scripts/extract/08_junction_tables.py

Build order:
    1. kanji_vocab    — scan each vocab word for known kanji characters in Python
    2. vocab_sentence — use indexed PostgreSQL substring searches per vocab word
    3. kanji_sentence — derive entirely from the first two junction tables

The script is idempotent: every insert uses ON CONFLICT DO NOTHING.
"""

import os

import psycopg
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

INSERT_BATCH_SIZE = 10_000
VOCAB_COMMIT_BATCH_SIZE = 250


def build_kanji_vocab(cursor: psycopg.Cursor) -> None:
    print("── Step 8a — kanji_vocab ────────────────────────────────────")

    cursor.execute("SELECT character FROM kanji")
    known_kanji = {row[0] for row in cursor.fetchall()}

    cursor.execute("SELECT id, word FROM vocab ORDER BY id")
    vocab_rows = cursor.fetchall()

    pairs: list[tuple[str, str]] = []

    for vocab_id, word in vocab_rows:
        unique_characters = set(word)

        for character in unique_characters:
            if character in known_kanji:
                pairs.append((character, vocab_id))

    inserted = 0
    for start in range(0, len(pairs), INSERT_BATCH_SIZE):
        batch = pairs[start : start + INSERT_BATCH_SIZE]
        cursor.executemany(
            """
            INSERT INTO kanji_vocab (kanji_char, vocab_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            batch,
        )
        inserted += cursor.rowcount
        print(
            f"  Processed {min(start + len(batch), len(pairs)):,}/{len(pairs):,} "
            f"pairs — {inserted:,} inserted"
        )

    cursor.connection.commit()
    cursor.execute("SELECT COUNT(*) FROM kanji_vocab")
    total = (cursor.fetchone() or (0,))[0]
    print(f"  kanji_vocab total: {total:,}")


def ensure_sentence_trigram_index(cursor: psycopg.Cursor) -> None:
    print("── Step 8b — sentence trigram index ─────────────────────────")
    print("  Enabling pg_trgm ...")
    cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    cursor.connection.commit()

    print("  Creating permanent GIN index on sentences.japanese ...")
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_sentences_japanese_trgm
        ON sentences USING GIN (japanese gin_trgm_ops)
        """
    )
    cursor.connection.commit()
    print("  Trigram index ready.")


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_vocab_sentence(cursor: psycopg.Cursor) -> None:
    print("── Step 8c — vocab_sentence ─────────────────────────────────")

    cursor.execute("SELECT id, word FROM vocab ORDER BY id")
    vocab_rows = cursor.fetchall()
    total_vocab = len(vocab_rows)
    inserted = 0

    for index, (vocab_id, word) in enumerate(vocab_rows, start=1):
        cursor.execute(
            """
            INSERT INTO vocab_sentence (vocab_id, sentence_id)
            SELECT %s, id
            FROM sentences
            WHERE japanese LIKE %s ESCAPE '\\'
            ON CONFLICT DO NOTHING
            """,
            (vocab_id, f"%{escape_like(word)}%"),
        )
        inserted += cursor.rowcount

        if index % VOCAB_COMMIT_BATCH_SIZE == 0:
            cursor.connection.commit()
            print(
                f"  Processed {index:,}/{total_vocab:,} vocab words "
                f"({index / total_vocab * 100:.1f}%) — {inserted:,} inserted"
            )

    cursor.connection.commit()
    cursor.execute("SELECT COUNT(*) FROM vocab_sentence")
    total = (cursor.fetchone() or (0,))[0]
    print(f"  vocab_sentence total: {total:,}")


def build_kanji_sentence(cursor: psycopg.Cursor) -> None:
    print("── Step 8d — kanji_sentence ─────────────────────────────────")
    cursor.execute(
        """
        INSERT INTO kanji_sentence (kanji_char, sentence_id)
        SELECT DISTINCT kv.kanji_char, vs.sentence_id
        FROM kanji_vocab kv
        JOIN vocab_sentence vs ON kv.vocab_id = vs.vocab_id
        ON CONFLICT DO NOTHING
        """
    )
    inserted = cursor.rowcount
    cursor.connection.commit()

    cursor.execute("SELECT COUNT(*) FROM kanji_sentence")
    total = (cursor.fetchone() or (0,))[0]
    print(f"  kanji_sentence total: {total:,} ({inserted:,} inserted this run)")


def main() -> None:
    print("Step 8 — Building junction tables ...")

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cursor:
            build_kanji_vocab(cursor)
            ensure_sentence_trigram_index(cursor)
            build_vocab_sentence(cursor)
            build_kanji_sentence(cursor)

            cursor.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM kanji_vocab),
                    (SELECT COUNT(*) FROM vocab_sentence),
                    (SELECT COUNT(*) FROM kanji_sentence)
                """
            )
            kanji_vocab, vocab_sentence, kanji_sentence = cursor.fetchone() or (0, 0, 0)

    print("── Summary ──────────────────────────────────────────────────")
    print(f"  kanji_vocab    : {kanji_vocab:,}")
    print(f"  vocab_sentence : {vocab_sentence:,}")
    print(f"  kanji_sentence : {kanji_sentence:,}")


if __name__ == "__main__":
    main()
