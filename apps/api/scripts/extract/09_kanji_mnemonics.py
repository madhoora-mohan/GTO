"""
Step 9 — Add hand-authored mnemonics to JLPT kanji.

Run from apps/api/.

Read-only context export:
    uv run scripts/extract/09_kanji_mnemonics.py --export-context

Validate that every current JLPT kanji has a mnemonic:
    uv run scripts/extract/09_kanji_mnemonics.py --validate

Update kanji.mnemonic after reviewing data/generated/jlpt_kanji_context.json:
    uv run scripts/extract/09_kanji_mnemonics.py --load

The script never writes to the database unless --load is provided explicitly.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

# Reviewable source of truth for Step 9.
# Each JSON record contains character, JLPT level, meanings, components, and mnemonic.
MNEMONICS_PATH = Path("data/generated/jlpt_kanji_context.json")


def read_mnemonics() -> list[dict[str, Any]]:
    """Read the reviewed mnemonic records from JSON."""
    records = json.loads(MNEMONICS_PATH.read_text(encoding="utf-8"))

    if not isinstance(records, list):
        raise ValueError(f"{MNEMONICS_PATH} must contain a JSON array.")

    return records


def fetch_jlpt_kanji_context() -> list[dict[str, Any]]:
    """Read JLPT kanji, meanings, and ordered components from the database."""
    query = """
        SELECT
            k.character,
            k.jlpt,
            k.meanings,
            COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'character', c.character,
                        'keyword', c.keyword,
                        'meaning', c.meaning
                    )
                    ORDER BY kc.position NULLS LAST, c.id
                ) FILTER (WHERE c.id IS NOT NULL),
                '[]'::jsonb
            ) AS components
        FROM kanji k
        LEFT JOIN kanji_component kc ON kc.kanji_char = k.character
        LEFT JOIN components c ON c.id = kc.component_id
        WHERE k.jlpt IS NOT NULL
        GROUP BY k.character, k.jlpt, k.meanings
        ORDER BY
            CASE k.jlpt
                WHEN 'N5' THEN 1
                WHEN 'N4' THEN 2
                WHEN 'N3' THEN 3
                WHEN 'N2' THEN 4
                WHEN 'N1' THEN 5
            END,
            k.frequency NULLS LAST,
            k.character
    """

    with psycopg.connect(DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(query)
            rows = cursor.fetchall()

    context: list[dict[str, Any]] = []

    for character, jlpt, meanings, components in rows:
        context.append(
            {
                "character": character,
                "jlpt": jlpt,
                "meanings": meanings,
                "components": components,
            }
        )

    return context


def export_context() -> None:
    """Refresh database context while preserving reviewed mnemonic text."""
    context = fetch_jlpt_kanji_context()
    existing_mnemonics: dict[str, str] = {}

    if MNEMONICS_PATH.exists():
        for item in read_mnemonics():
            mnemonic = item.get("mnemonic")
            if isinstance(mnemonic, str) and mnemonic.strip():
                existing_mnemonics[item["character"]] = mnemonic

    for item in context:
        item["mnemonic"] = existing_mnemonics.get(item["character"], "")

    MNEMONICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    MNEMONICS_PATH.write_text(
        json.dumps(context, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {len(context):,} JLPT kanji to {MNEMONICS_PATH}")


def validate_mnemonics(
    context: list[dict[str, Any]],
    mnemonic_records: list[dict[str, Any]],
) -> None:
    """Require exactly one complete mnemonic entry for every current JLPT kanji."""
    expected_by_character: dict[str, dict[str, Any]] = {}
    for item in context:
        character = item.get("character")
        if not isinstance(character, str):
            raise ValueError("Database context contains an invalid character.")
        expected_by_character[character] = item

    expected_characters = set(expected_by_character)
    records_by_character: dict[str, dict[str, Any]] = {}
    for item in mnemonic_records:
        character = item.get("character")
        if not isinstance(character, str) or character in records_by_character:
            raise ValueError(
                "Mnemonic JSON contains an invalid or duplicate character record."
            )
        records_by_character[character] = item

    authored_characters = set(records_by_character)

    missing = sorted(expected_characters - authored_characters)
    unexpected = sorted(authored_characters - expected_characters)
    invalid: list[str] = []
    stale_context: list[str] = []

    for character, entry in records_by_character.items():
        jlpt = entry.get("jlpt")
        meanings = entry.get("meanings")
        components = entry.get("components")
        mnemonic = entry.get("mnemonic")

        if (
            not isinstance(jlpt, str)
            or not isinstance(meanings, list)
            or not meanings
            or not isinstance(components, list)
            or not isinstance(mnemonic, str)
            or not mnemonic.strip()
        ):
            invalid.append(character)
            continue

        expected = expected_by_character.get(character)
        if expected is None:
            continue

        if (
            jlpt != expected["jlpt"]
            or meanings != expected["meanings"]
            or components != expected["components"]
        ):
            stale_context.append(character)

    if missing or unexpected or invalid or stale_context:
        messages = []
        if missing:
            messages.append(f"missing={len(missing)} ({''.join(missing[:20])})")
        if unexpected:
            messages.append(
                f"unexpected={len(unexpected)} ({''.join(unexpected[:20])})"
            )
        if invalid:
            messages.append(f"invalid={len(invalid)} ({''.join(invalid[:20])})")
        if stale_context:
            messages.append(
                f"stale_context={len(stale_context)} "
                f"({''.join(stale_context[:20])})"
            )
        raise ValueError("Mnemonic validation failed: " + "; ".join(messages))

    print(f"Validated {len(authored_characters):,} JLPT kanji mnemonics.")


def load_mnemonics() -> None:
    """Validate and update kanji.mnemonic in one transaction."""
    context = fetch_jlpt_kanji_context()
    mnemonic_records = read_mnemonics()
    validate_mnemonics(context, mnemonic_records)

    rows = [
        (entry["mnemonic"].strip(), entry["character"])
        for entry in mnemonic_records
    ]

    with psycopg.connect(DB_URL) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                UPDATE kanji
                SET mnemonic = %s
                WHERE character = %s AND jlpt IS NOT NULL
                """,
                rows,
            )

            if cursor.rowcount != len(rows):
                raise RuntimeError(
                    f"Expected to update {len(rows):,} kanji, "
                    f"but PostgreSQL reported {cursor.rowcount:,}."
                )

        connection.commit()

    print(f"Updated {len(rows):,} JLPT kanji mnemonics.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--export-context",
        action="store_true",
        help="Read JLPT kanji context and write it to local JSON.",
    )
    action.add_argument(
        "--validate",
        action="store_true",
        help="Check mnemonic coverage without updating the database.",
    )
    action.add_argument(
        "--load",
        action="store_true",
        help="Validate and update kanji.mnemonic in the database.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.export_context:
        export_context()
    elif args.validate:
        validate_mnemonics(fetch_jlpt_kanji_context(), read_mnemonics())
    elif args.load:
        load_mnemonics()


if __name__ == "__main__":
    main()
