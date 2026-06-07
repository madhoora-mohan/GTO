"""
Step 6b — Overlay JLPT levels onto `kanji` and `vocab` tables.

Run from apps/api/:
    uv run scripts/extract/06b_jlpt_overlay.py

Sources:
- kanji JLPT  ← kanjium/data/source_files/kanjidict.txt (tab-separated, column 14)
- vocab JLPT  ← open-anki-jlpt-decks/src/n1.csv ... n5.csv (expression column)

Notes:
- kanjidict.txt column 14 has values like "N1 (advanced)", "N2 (intermediate)" etc.
  We extract just the "N1"–"N5" prefix.
- For vocab, we match on vocab.word against the expression column in each CSV.
  We process N5 → N1 in order, so if a word appears in multiple levels the
  highest (most advanced) level wins (last write wins).
- Script is idempotent — re-running just overwrites with the same values.
"""

import csv
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

RAW = Path("data/raw")
KANJIDICT = RAW / "kanjium/data/source_files/kanjidict.txt"
JLPT_VOCAB_DIR = RAW / "open-anki-jlpt-decks/src"


def overlay_kanji_jlpt(cursor):
    print("Overlaying JLPT levels onto kanji table ...")

    updated = 0

    with open(KANJIDICT, encoding="utf-8") as f:
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 14:
                continue

            character = cols[0].strip()
            jlpt_raw = cols[13].strip()  # e.g. "N1 (advanced)"

            if not jlpt_raw or not jlpt_raw.startswith("N"):
                continue

            # Extract just "N1", "N2" etc. from "N1 (advanced)"
            jlpt = jlpt_raw.split()[0]  # "N1 (advanced)" → "N1"

            if jlpt not in ("N1", "N2", "N3", "N4", "N5"):
                continue

            cursor.execute(
                "UPDATE kanji SET jlpt = %s WHERE character = %s",
                (jlpt, character),
            )
            if cursor.rowcount > 0:
                updated += 1

    print(f"  Updated {updated} kanji rows with JLPT level.")


def overlay_vocab_jlpt(cursor):
    print("Overlaying JLPT levels onto vocab table ...")

    total_updated = 0

    # Process N1 first, N5 last — so N5 wins if a word appears in multiple levels
    # (least advanced / easiest level takes precedence)
    for level in ["N1", "N2", "N3", "N4", "N5"]:
        csv_file = JLPT_VOCAB_DIR / f"{level.lower()}.csv"
        if not csv_file.exists():
            print(f"  {level}: file not found, skipping.")
            continue

        updated = 0
        with open(csv_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                expression = row.get("expression", "").strip()
                if not expression:
                    continue

                cursor.execute(
                    "UPDATE vocab SET jlpt = %s WHERE word = %s",
                    (level, expression),
                )
                if cursor.rowcount > 0:
                    updated += 1

        print(f"  {level}: {updated} vocab rows updated.")
        total_updated += updated

    print(f"  Total vocab rows with JLPT: {total_updated}")


def main():
    print("Connecting to database ...")
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cursor:

            overlay_kanji_jlpt(cursor)
            conn.commit()

            overlay_vocab_jlpt(cursor)
            conn.commit()

            # Verification
            cursor.execute("SELECT COUNT(*) FROM kanji WHERE jlpt IS NOT NULL")
            kanji_with_jlpt = (cursor.fetchone() or (0,))[0]

            cursor.execute("SELECT COUNT(*) FROM vocab WHERE jlpt IS NOT NULL")
            vocab_with_jlpt = (cursor.fetchone() or (0,))[0]

            print("── Summary ──────────────────────────────────────────────")
            print(f"  Kanji with JLPT level : {kanji_with_jlpt}")
            print(f"  Vocab with JLPT level : {vocab_with_jlpt}")


if __name__ == "__main__":
    main()
