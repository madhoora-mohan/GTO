"""
Step 7 — Extract Tatoeba sentences → `sentences` table.

Run from apps/api/:
    uv run scripts/extract/07_sentences.py

---------------------------------------------------------------------------
WHAT THIS SCRIPT DOES (plain English)
---------------------------------------------------------------------------
Tatoeba is a giant crowd-sourced collection of sentences in many languages.
We only want Japanese sentences that have an English translation.

The data comes in three separate files:
  1. tatoeba_jpn_sentences.tsv.bz2  — all Japanese sentences
  2. tatoeba_eng_sentences.tsv.bz2  — all English sentences
  3. tatoeba_links.tar.bz2          — which sentences are translations of each other

Each sentence has a numeric ID. The links file tells us, for example:
  "sentence 4703 is a translation of sentence 1277"
But it doesn't say which language each sentence is — we have to cross-reference
against the sentence files to figure out if a pair is Japanese ↔ English.

STRATEGY:
  Step A — Load ALL Japanese sentences into memory (248k rows, ~30 MB).
  Step B — Load ALL English sentences into memory (2M rows, ~400 MB).
            This is a linear scan of the file from top to bottom — expected.
  Step C — Stream through all 28 million links one by one.
            For each link, check: is one side Japanese and the other English?
            If yes, record it as a matched pair.
  Step D — Insert all matched pairs into the `sentences` table in batches.

WHY load both sentence files into memory first?
  The links file contains pairs from ALL languages (French, Spanish, Arabic...).
  To know whether a sentence is English, we need the English dict already loaded.
  We can't do a "find only the English ones" pass during the scan because the
  links don't carry language information — just IDs.

WHY open the DB connection AFTER all the scanning?
  Steps A–C take ~10 minutes. If we opened the DB connection at the start and
  then sat idle for 10 minutes, Neon (our cloud database) would close the
  connection due to inactivity — exactly what killed script 06c previously.
"""

import bz2       # bz2 = a compression format (like zip). Our .bz2 files are compressed TSVs.
import io        # io = tools for reading streams of data
import os
import tarfile   # tarfile = reads .tar.bz2 archives (like a zip file that also compresses)
from pathlib import Path

import psycopg         # psycopg = the Python library for talking to PostgreSQL
from dotenv import load_dotenv

load_dotenv()  # reads our .env file so DATABASE_URL is available
# SQLAlchemy (our ORM) adds "+asyncpg" to the URL. psycopg doesn't want that — strip it.
DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

RAW = Path("data/raw")
JPY_FILE = RAW / "tatoeba_jpn_sentences.tsv.bz2"
ENG_FILE = RAW / "tatoeba_eng_sentences.tsv.bz2"
LINKS_FILE = RAW / "tatoeba_links.tar.bz2"

# How many rows to send to the database in one go.
# Sending one row at a time = too many round-trips (slow).
# Sending all at once = connection timeout (what broke 06c).
# 5000 at a time = a good middle ground.
BATCH_SIZE = 5000


def load_sentences(path: Path) -> dict[int, str]:
    """
    Read a .tsv.bz2 sentence file and return a dict: { sentence_id → text }.

    Each line in the file looks like:
        4703\tjpn\t私は眠らなければなりません。
        ^^^^  ^^^  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        ID    lang  the actual sentence text

    TSV = Tab-Separated Values. The columns are separated by the \t tab character.
    We split on \t with maxsplit=2 so that a stray tab inside the sentence text
    doesn't accidentally split the sentence into extra columns.
    """
    sentences: dict[int, str] = {}
    with bz2.open(path, "rt", encoding="utf-8") as f:
        # bz2.open decompresses the file on the fly as we read it line by line.
        # We never load the whole compressed file into memory at once.
        for line in f:
            parts = line.rstrip("\n").split("\t", 2)  # maxsplit=2 → at most 3 parts
            if len(parts) < 3:
                continue  # skip any malformed lines
            sentence_id = int(parts[0])
            text = parts[2]  # parts[1] is the language code — we don't need it
            sentences[sentence_id] = text
    return sentences


def main():
    print("── Step 7 — Tatoeba sentences ───────────────────────────────")

    # ── Step A: Load Japanese sentences ──────────────────────────────────────
    # This is a linear scan of the file from top to bottom.
    # Result: a dict like { 4703: "私は眠らなければなりません。", 4704: "何してるの？", ... }
    print(f"Loading {JPY_FILE} ...")
    jpn = load_sentences(JPY_FILE)
    print(f"  Loaded {len(jpn):,} Japanese sentences.")

    # ── Step B: Load English sentences ───────────────────────────────────────
    # Also a linear scan of the file from top to bottom — expected and fine.
    # The file is larger (~2M rows, ~400 MB in memory) but modern machines handle this easily.
    # We MUST load this before scanning links — see the module docstring for why.
    print(f"Loading {ENG_FILE} ...")
    eng = load_sentences(ENG_FILE)
    print(f"  Loaded {len(eng):,} English sentences.")

    # ── Step C: Scan the links file ───────────────────────────────────────────
    # The links file is a .tar.bz2 archive (a compressed bundle of files).
    # Each line looks like:   4703\t1277
    # Meaning: sentence 4703 and sentence 1277 are translations of each other.
    # The relationship is symmetric — (A, B) and (B, A) can both appear.
    # There are 28 million lines total (all language pairs, not just Japanese/English).
    print(f"Scanning {LINKS_FILE} ...")

    # pairs will hold: { japanese_sentence_id → english_sentence_id }
    # Only one English translation per Japanese sentence (first match wins).
    pairs: dict[int, int] = {}
    total_links = 0

    with tarfile.open(LINKS_FILE, "r:bz2") as tar:
        for member in tar.getmembers():
            f = tar.extractfile(member)
            if f is None:
                continue
            for line in io.TextIOWrapper(f, encoding="utf-8"):
                parts = line.rstrip("\n").split("\t", 1)
                if len(parts) != 2:
                    continue

                a, b = int(parts[0]), int(parts[1])
                total_links += 1

                if total_links % 2_000_000 == 0:
                    print(f"  ... {total_links:,} links scanned — {len(pairs):,} jpn→eng pairs found so far")

                # Check direction 1: a is Japanese, b is English
                # .setdefault(key, value) means: "if this key isn't in the dict yet,
                # add it with this value. If it's already there, do nothing."
                # This gives us the FIRST English translation we encounter per Japanese sentence.
                # Tatoeba's links file is roughly quality-ordered, so first = best.
                if a in jpn and b in eng:
                    pairs.setdefault(a, b)

                # Check direction 2: b is Japanese, a is English (link went the other way)
                elif b in jpn and a in eng:
                    pairs.setdefault(b, a)

    print(f"  Done. Scanned {total_links:,} links total.")
    print(f"  Found {len(pairs):,} unique Japanese sentences with an English translation.")

    # ── Step D: Insert into the database ──────────────────────────────────────
    # We open the DB connection HERE — after all the heavy scanning is done.
    # This avoids holding an idle connection for 10+ minutes (which caused 06c to crash).
    print("Connecting to database and inserting ...")

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cursor:
            total_inserted = 0
            batch_num = 0
            batch: list[tuple] = []
            total_pairs = len(pairs)

            for jpn_id, eng_id in pairs.items():
                # Build a tuple of (id, japanese_text, english_text) for this row
                batch.append((jpn_id, jpn[jpn_id], eng[eng_id]))
                # jlpt is left NULL for all Tatoeba rows — we don't infer it here.
                # source defaults to 'tatoeba' in the DB schema, so we don't pass it either.

                if len(batch) == BATCH_SIZE:
                    batch_num += 1
                    cursor.executemany(
                        """
                        INSERT INTO sentences (id, japanese, english, source)
                        VALUES (%s, %s, %s, 'tatoeba')
                        ON CONFLICT (id) DO NOTHING
                        """,
                        # ON CONFLICT DO NOTHING = if a sentence with this ID already exists,
                        # skip it silently. Makes the script safe to re-run (idempotent).
                        # source = 'tatoeba' is passed explicitly because the DB column is
                        # NOT NULL — we can't rely on the default being applied.
                        batch,
                    )
                    conn.commit()  # save this batch to the DB permanently
                    total_inserted += cursor.rowcount
                    processed = min(batch_num * BATCH_SIZE, total_pairs)
                    pct = processed / total_pairs * 100
                    print(f"  Batch {batch_num} — {cursor.rowcount}/{BATCH_SIZE} inserted — {processed:,}/{total_pairs:,} ({pct:.1f}%) — {total_inserted:,} total")
                    batch = []

            # The last batch will almost certainly be smaller than BATCH_SIZE.
            # We flush it here so we don't lose the final rows.
            if batch:
                batch_num += 1
                cursor.executemany(
                    """
                    INSERT INTO sentences (id, japanese, english, source)
                    VALUES (%s, %s, %s, 'tatoeba')
                    ON CONFLICT (id) DO NOTHING
                    """,
                    batch,
                )
                conn.commit()
                total_inserted += cursor.rowcount
                print(f"  Batch {batch_num} (final) — {cursor.rowcount}/{len(batch)} inserted — {total_inserted:,} total")

            # Final count straight from the DB — the ground truth.
            cursor.execute("SELECT COUNT(*) FROM sentences")
            db_total = (cursor.fetchone() or (0,))[0]

    print("── Summary ──────────────────────────────────────────────────")
    print(f"  sentences table total : {db_total:,}")


if __name__ == "__main__":
    main()
