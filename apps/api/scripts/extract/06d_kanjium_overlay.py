"""
Step 6d — Overlay numeric frequency ranks from Kanjium → `kanji` table.

Run from apps/api/:
    uv run scripts/extract/06d_kanjium_overlay.py

Source: data/raw/kanjium/data/kanjidb.sqlite (kanjidict table, `frequency` column)

Kanjium assigns a numeric frequency rank to each kanji based on corpus frequency
(novels + Wikipedia). Rank 1 = most common kanji overall. The `kanji.frequency`
column is filled here.

Note: Kanjium's frequency data for vocab words is text ("Very common*", "Common",
etc.) and is not used — vocab.frequency comes from JMdict priority tags.

Script is idempotent — re-running overwrites with the same values.
"""

import os
import sqlite3
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

KANJIUM_DB = Path("data/raw/kanjium/data/kanjidb.sqlite")


def main():
    print("Step 6d — Kanjium frequency ranks onto kanji ...")

    print(f"  Reading {KANJIUM_DB} ...")
    with sqlite3.connect(KANJIUM_DB) as kanjium:
        rows = kanjium.execute(
            "SELECT kanji, CAST(frequency AS INTEGER) FROM kanjidict WHERE frequency != ''"
        ).fetchall()
    print(f"  Found {len(rows)} kanji with numeric frequency ranks.")

    print("  Connecting to Neon ...")
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                "UPDATE kanji SET frequency = %s WHERE character = %s",
                [(rank, char) for char, rank in rows],
            )
            conn.commit()

            cursor.execute("SELECT COUNT(*) FROM kanji WHERE frequency IS NOT NULL")
            filled = (cursor.fetchone() or (0,))[0]
            cursor.execute("SELECT COUNT(*) FROM kanji")
            total = (cursor.fetchone() or (0,))[0]

    print("── Summary ──────────────────────────────────────────────")
    print(f"  kanji.frequency filled : {filled} / {total}")


if __name__ == "__main__":
    main()
