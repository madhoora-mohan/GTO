"""
Step 4 — Extract KANJIDIC2 → `kanji` table.

Run from apps/api/:
    uv run python scripts/extract/04_kanji.py

Source: data/raw/kanjidic2.xml.gz
Inserts one row per kanji character with readings, meanings, stroke count,
grade, frequency, and classical radical number.

Notes:
- We deliberately SKIP the <jlpt> field from KANJIDIC2. It uses the old 1–4
  numbering system. The N5–N1 levels are overlaid in Step 6b from Tanos/Waller.
- unicode_hex is read from the <cp_value cp_type="ucs"> element in the XML.
- classical_radical_char is looked up from the components table using
  classical_radical_number — so Step 3 must have run before this.
- stroke_order_svg_url and mnemonic are left NULL here; filled in Steps 9 + 10.
- Script is idempotent: ON CONFLICT DO NOTHING means re-runs are safe.
"""

import gzip
import json
import os
from pathlib import Path
from xml.etree import ElementTree as ET

import psycopg
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

RAW = Path("data/raw")
KANJIDIC2_GZ = RAW / "kanjidic2.xml.gz"


def main():
    print("Connecting to database ...")
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cursor:

            # Build a lookup: classical radical number → character
            # e.g. {1: '一', 9: '人', 85: '水', ...}
            # Used to populate classical_radical_char from the radical number.
            cursor.execute(
                "SELECT id, character FROM components WHERE id IS NOT NULL"
            )
            # Note: components.id is a SERIAL, not the radical number.
            # KANJIDIC2 gives us the Kangxi radical number (1–214).
            # We don't have a direct radical-number → character mapping in our DB,
            # so classical_radical_char will be left NULL here and can be patched
            # later if needed. The radical number itself is still stored.

            print(f"Parsing {KANJIDIC2_GZ} ...")
            with gzip.open(KANJIDIC2_GZ, "rb") as f:
                tree = ET.parse(f)

            root = tree.getroot()
            characters = root.findall(".//character")
            print(f"  Found {len(characters)} characters in KANJIDIC2.")

            # Parse all characters into a list of tuples first, then insert in one batch.
            # This is much faster than 13,000 individual round-trips to the remote DB.
            rows = []
            skipped = 0

            print("  Parsing XML entries ...")
            for char_elem in characters:
                literal = char_elem.findtext("literal")
                if not literal:
                    continue

                unicode_hex = char_elem.findtext('.//cp_value[@cp_type="ucs"]')
                if not unicode_hex:
                    continue

                # On'yomi readings (Chinese-origin), e.g. ['シン']
                onyomi = [
                    r.text
                    for r in char_elem.findall('.//reading[@r_type="ja_on"]')
                    if r.text
                ]

                # Kun'yomi readings (Japanese-origin), e.g. ['あたら.しい', 'あら.た']
                kunyomi = [
                    r.text
                    for r in char_elem.findall('.//reading[@r_type="ja_kun"]')
                    if r.text
                ]

                # Name readings (nanori), e.g. ['あらた']
                nanori = [
                    n.text
                    for n in char_elem.findall(".//nanori")
                    if n.text
                ]

                # English meanings only (m_lang attribute absent = English)
                meanings = [
                    m.text
                    for m in char_elem.findall(".//meaning")
                    if m.get("m_lang") is None and m.text
                ]

                if not meanings:
                    skipped += 1
                    continue

                stroke_count_text = char_elem.findtext(".//stroke_count")
                stroke_count = int(stroke_count_text) if stroke_count_text else None
                if not stroke_count:
                    skipped += 1
                    continue

                # School grade (1–6 elementary, 8 = middle school)
                grade_text = char_elem.findtext(".//grade")
                grade = int(grade_text) if grade_text else None

                # Frequency rank out of the 2,500 most-used kanji
                freq_text = char_elem.findtext(".//freq")
                frequency = int(freq_text) if freq_text else None

                # Classical (Kangxi) radical number, e.g. 75 for 木
                radical_text = char_elem.findtext('.//rad_value[@rad_type="classical"]')
                classical_radical_number = int(radical_text) if radical_text else None

                rows.append((
                    literal,
                    unicode_hex,
                    json.dumps(meanings),
                    json.dumps(onyomi),
                    json.dumps(kunyomi),
                    json.dumps(nanori),
                    grade,
                    stroke_count,
                    frequency,
                    classical_radical_number,
                ))

            print(f"  Parsed {len(rows)} rows, skipped {skipped}. Inserting ...")

            # executemany sends all rows in one batch — far fewer round-trips
            cursor.executemany(
                """
                INSERT INTO kanji (
                    character, unicode_hex, meanings, onyomi, kunyomi, nanori,
                    grade, stroke_count, frequency, classical_radical_number
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (character) DO NOTHING
                """,
                rows,
            )
            conn.commit()

            print(f"  Done — {len(rows)} rows sent to DB.")

            # Verification
            cursor.execute("SELECT COUNT(*) FROM kanji")
            total = (cursor.fetchone() or (0,))[0]

            cursor.execute("SELECT COUNT(*) FROM kanji WHERE jlpt IS NOT NULL")
            with_jlpt = (cursor.fetchone() or (0,))[0]

            print("── Summary ──────────────────────────────────────────────")
            print(f"  Total kanji in DB : {total}")
            print(f"  With JLPT level   : {with_jlpt} (expected 0 — overlaid in Step 6b)")


if __name__ == "__main__":
    main()
