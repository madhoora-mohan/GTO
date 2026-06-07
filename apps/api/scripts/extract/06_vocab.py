"""
Step 6 — Extract JMdict → `vocab` table (JLPT words only).

Run from apps/api/:
    uv run scripts/extract/06_vocab.py

Sources:
- data/raw/JMdict_e.gz                        — main dictionary
- data/raw/open-anki-jlpt-decks/src/n1..n5.csv — JLPT word lists

Why JLPT-only?
JMdict has ~217k entries; only ~7.6k are JLPT words (N5–N1). This app is
JLPT-focused, so we pre-filter at import time rather than importing 217k rows
and pruning later.

We load all JLPT expressions from the same CSV files that Step 6b uses.
If a JMdict entry's display word matches any expression in those CSVs, we
keep it. Everything else is skipped.

What we insert here:
- id         ← ent_seq (JMdict sequence number)
- word       ← first kanji form, or first reading if no kanji form
- reading    ← first reading element
- romaji     ← romaji transliteration (pykakasi)
- meanings   ← array of {pos, definitions} objects (JSONB)
- is_common  ← true if tagged ichi1/news1/spec1

What is NOT inserted here (overlaid in later steps):
- jlpt     ← Step 6b (Tanos/Waller)
- furigana ← Step 6c (JmdictFurigana)
- tags     ← not populated (low priority for MVP)

Script is idempotent: ON CONFLICT DO NOTHING.
"""

import csv
import gzip
import json
import os
from pathlib import Path
from xml.etree import ElementTree as ET

import psycopg
import pykakasi
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

RAW = Path("data/raw")
JMDICT_GZ = RAW / "JMdict_e.gz"
JLPT_VOCAB_DIR = RAW / "open-anki-jlpt-decks/src"

# JLPT levels to include — same files Step 6b reads
JLPT_LEVELS = ["N1", "N2", "N3", "N4", "N5"]


def load_jlpt_words() -> set[str]:
    """
    Read every JLPT CSV and collect all expression values into a set.
    These are the words we want — JMdict entries not in this set are skipped.
    """
    words: set[str] = set()
    for level in JLPT_LEVELS:
        csv_file = JLPT_VOCAB_DIR / f"{level.lower()}.csv"
        if not csv_file.exists():
            print(f"  Warning: {csv_file} not found, skipping {level}.")
            continue
        with open(csv_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                expression = row.get("expression", "").strip()
                if expression:
                    words.add(expression)
    return words


def main():
    # Load JLPT word list BEFORE touching JMdict.
    # We use this set to skip non-JLPT entries during parsing.
    print("Loading JLPT word lists ...")
    jlpt_words = load_jlpt_words()
    print(f"  {len(jlpt_words)} unique JLPT expressions loaded.")

    # pykakasi converts kana → romaji.
    # Initialised once outside the loop — loading its dictionary is expensive.
    kks = pykakasi.kakasi()

    print("Connecting to database ...")
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cursor:
            print(f"Parsing {JMDICT_GZ} ...")
            with gzip.open(JMDICT_GZ, "rb") as f:
                tree = ET.parse(f)

            entries = tree.findall("entry")
            print(f"  Found {len(entries)} entries in JMdict.")
            print("  Building rows (JLPT-only filter active) ...")

            rows = []
            skipped_no_reading = 0
            skipped_no_meanings = 0
            skipped_not_jlpt = 0

            for entry in entries:
                seq = entry.findtext("ent_seq")
                if not seq:
                    continue

                # Kanji forms (written forms with kanji), e.g. ['食べる', '喰べる']
                kanji_forms = [
                    k.findtext("keb")
                    for k in entry.findall("k_ele")
                    if k.findtext("keb")
                ]

                # Reading elements (kana-only readings), e.g. ['たべる']
                readings = [
                    r.findtext("reb")
                    for r in entry.findall("r_ele")
                    if r.findtext("reb")
                ]

                if not readings:
                    skipped_no_reading += 1
                    continue

                # Use first kanji form as the display word; fall back to first reading.
                # This is the value Step 6b matches against when overlaying JLPT levels,
                # so it must be computed the same way here for the filter to work.
                word = kanji_forms[0] if kanji_forms else readings[0]
                reading = readings[0]

                # ── JLPT filter ───────────────────────────────────────────────
                # Skip any entry whose display word is not in the JLPT word list.
                # Step 6b uses the same word → expression match, so this is safe.
                if word not in jlpt_words:
                    skipped_not_jlpt += 1
                    continue
                # ─────────────────────────────────────────────────────────────

                # Convert kana reading to romaji.
                # e.g. 'たべる' → 'taberu'
                romaji = "".join(item["hepburn"] for item in kks.convert(reading or ""))

                # is_common: true if tagged ichi1/news1/spec1 — the ~10k most
                # practically useful words in JMdict.
                priorities = [
                    p.text
                    for k in entry.findall("k_ele")
                    for p in k.findall("ke_pri")
                    if p.text
                ]
                # Also check reading priorities for kana-only words
                priorities += [
                    p.text
                    for r in entry.findall("r_ele")
                    for p in r.findall("re_pri")
                    if p.text
                ]
                is_common = any(p in ("ichi1", "news1", "spec1") for p in priorities)

                # meanings: array of {pos, definitions} objects
                # e.g. [{"pos": ["v1"], "definitions": ["to eat", "to live on"]}]
                meanings = []
                for sense in entry.findall("sense"):
                    pos = [p.text for p in sense.findall("pos") if p.text]
                    definitions = [
                        g.text
                        for g in sense.findall("gloss")
                        if g.get("{http://www.w3.org/XML/1998/namespace}lang", "eng")
                        == "eng"
                        and g.text
                    ]
                    if definitions:
                        meanings.append({"pos": pos, "definitions": definitions})

                if not meanings:
                    skipped_no_meanings += 1
                    continue

                rows.append(
                    (
                        seq,
                        word,
                        reading,
                        romaji or None,
                        json.dumps(meanings),
                        is_common,
                    )
                )

            print(f"  Parsed {len(rows)} JLPT rows.")
            print(f"  Skipped: {skipped_not_jlpt} not in JLPT list, "
                  f"{skipped_no_reading} no reading, {skipped_no_meanings} no meanings.")
            print("  Inserting ...")

            cursor.executemany(
                """
                INSERT INTO vocab (id, word, reading, romaji, meanings, is_common)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                rows,
            )
            conn.commit()

            # Verification
            cursor.execute("SELECT COUNT(*) FROM vocab")
            total = (cursor.fetchone() or (0,))[0]

            cursor.execute("SELECT COUNT(*) FROM vocab WHERE is_common = true")
            common = (cursor.fetchone() or (0,))[0]

            print("── Summary ──────────────────────────────────────────────")
            print(f"  Total vocab in DB : {total}")
            print(f"  Common words      : {common}")
            print("  With JLPT         : 0 (expected — overlaid in Step 6b)")


if __name__ == "__main__":
    main()
