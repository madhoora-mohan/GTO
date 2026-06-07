"""
Step 3 — Populate the `components` table.

Run from apps/api/:
    uv run python scripts/extract/03_components.py

Three sub-steps, run in sequence:
  3a  Insert all 253 components with stroke_count from krad_components.json
  3b  Overlay meaning + keyword from japanese-radicals.csv (~200 matches)
  3c  LLM gap-fill — Claude Code fills remaining NULLs in-session (no API call here)
      This script prints any components still missing meaning so you know what to hand
      to Claude Code.

The script is idempotent — safe to re-run after a partial failure.
"""

import csv
import json
import os
import unicodedata
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# ── Environment ───────────────────────────────────────────────────────────────

load_dotenv()  # reads apps/api/.env

# DATABASE_URL in .env may carry "+asyncpg" (SQLAlchemy prefix).
# psycopg v3 needs a plain postgresql:// URL, so we strip the driver prefix.
DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

# Paths are relative to the repo root apps/api/ directory.
RAW = Path("data/raw")
KRAD_COMPONENTS_JSON = RAW / "krad_components.json"
JAPANESE_RADICALS_CSV = RAW / "japanese-radicals.csv"


# ── Step 3a — Insert components with stroke_count ─────────────────────────────
#
# krad_components.json contains all 253 components that appear in KRADFILE,
# each with a strokeCount value. This is the authoritative source for stroke counts.
#
# We INSERT here. If a component already exists (re-run), we UPDATE stroke_count
# so this step is always idempotent.


def step_3a(cursor):
    print("Step 3a — inserting components from krad_components.json ...")

    with open(KRAD_COMPONENTS_JSON, encoding="utf-8") as f:
        entries = json.load(f)

    for entry in entries:
        character = entry["component"]
        stroke_count = entry["strokeCount"]

        cursor.execute(
            """
            INSERT INTO components (character, stroke_count, keyword, meaning)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (character)
                DO UPDATE SET stroke_count = EXCLUDED.stroke_count
            """,
            (character, stroke_count, "?", "?"),
        )

    print(f"  {len(entries)} components upserted with stroke_count.")


# ── Step 3b — Overlay meaning + keyword from japanese-radicals.csv ────────────
#
# The CSV from kanjialive covers ~200 of the 253 KRADFILE components (the ones
# that correspond to traditional Kangxi radicals). For each matching row we:
#   - Set `meaning` from the "Meaning" column (e.g. "one, horizontal stroke")
#   - Derive `keyword` as the first word of the meaning, lowercased
#     (e.g. "one, horizontal stroke" → "one")
#     This short keyword is what the LLM uses when generating kanji mnemonics.
#
# The CSV uses Kangxi radical codepoints (U+2F00 range) but KRADFILE uses regular
# CJK codepoints. NFKC normalization maps Kangxi → CJK, giving ~206 matches.
# The remaining ~47 are KRADFILE-only components handled in step 3c.


def step_3b(cursor):
    print("Step 3b — overlaying meaning + keyword from japanese-radicals.csv ...")

    updated = 0

    with open(JAPANESE_RADICALS_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # The CSV uses Kangxi radical codepoints (U+2F00 range, e.g. ⼀)
            # but KRADFILE uses regular CJK codepoints (e.g. 一).
            # NFKC normalization maps Kangxi → CJK, giving us ~206 matches.
            character = unicodedata.normalize("NFKC", row["Radical"].strip())
            meaning = row["Meaning"].strip()

            if not character or not meaning:
                continue

            # keyword = first meaningful word from the meaning string
            # e.g. "one, horizontal stroke" → "one"
            # e.g. "water (3-stroke variant)" → "water"
            keyword = meaning.split(",")[0].split("(")[0].strip().lower()

            cursor.execute(
                """
                UPDATE components
                SET meaning = %s, keyword = %s
                WHERE character = %s
                """,
                (meaning, keyword, character),
            )
            # rowcount tells us if the UPDATE actually matched a row
            if cursor.rowcount > 0:
                updated += 1

    print(f"  {updated} components updated with meaning + keyword from CSV.")


# ── Step 3c — Report any components still missing meaning (for LLM gap-fill) ──
#
# Some KRADFILE components have no match in the Kangxi radical CSV — they're
# KRADFILE-specific decomposition elements. Their meaning + keyword must be
# supplied by Claude Code directly in the build session (no API call needed).
#
# This function prints the list so you can hand it to Claude Code.


def step_3c_report(cursor):
    print("Step 3c — checking for components still missing meaning ...")

    cursor.execute(
        "SELECT character, stroke_count FROM components WHERE meaning IS NULL ORDER BY stroke_count, character"
    )
    missing = cursor.fetchall()

    if not missing:
        print("  All 253 components have meaning + keyword. Nothing left to fill.")
        return

    print(
        f"  {len(missing)} components still missing meaning — hand these to Claude Code for gap-fill:"
    )
    print()
    print(f"  {'char':<6} stroke_count")
    print(f"  {'────':<6} ────────────")
    for char, strokes in missing:
        print(f"  {char:<6} {strokes}")
    print()
    print(
        "  Paste this list to Claude Code and ask it to provide keyword + meaning for each."
    )


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    print(f"Connecting to database ...")
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cursor:
            # 3a — insert all 253 with stroke counts
            step_3a(cursor)
            conn.commit()

            # 3b — overlay meaning + keyword from kanjialive CSV
            step_3b(cursor)
            conn.commit()

            # 3c — report what's still missing (Claude Code fills these in-session)
            step_3c_report(cursor)

            # ── Final count ───────────────────────────────────────────────────
            cursor.execute("SELECT COUNT(*) FROM components")
            total = (cursor.fetchone() or (0,))[0]

            cursor.execute("SELECT COUNT(*) FROM components WHERE meaning IS NOT NULL")
            with_meaning = (cursor.fetchone() or (0,))[0]

            print("── Summary ──────────────────────────────────────────────")
            print(f"  Total components in DB : {total}")
            print(f"  With meaning + keyword : {with_meaning}")
            print(f"  Still missing meaning  : {total - with_meaning}")


if __name__ == "__main__":
    main()
