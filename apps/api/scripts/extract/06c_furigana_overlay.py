"""
Step 6c — Overlay furigana onto `vocab` table from JmdictFurigana.

Run from apps/api/:
    uv run scripts/extract/06c_furigana_overlay.py

Source: data/raw/JmdictFurigana.json

JmdictFurigana provides pre-computed furigana breakdowns for vocab words.
Each entry looks like:
    {
        "text": "食べる",
        "reading": "たべる",
        "furigana": [{"ruby": "食", "rt": "た"}, {"ruby": "べる"}]
    }

We match on both `text` (word) AND `reading` to avoid ambiguity —
the same word can have multiple readings with different furigana.

The furigana array is stored as-is into vocab.furigana (JSONB).
Script is idempotent — re-running overwrites with the same values.
"""

import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

RAW = Path("data/raw")
FURIGANA_JSON = RAW / "JmdictFurigana.json"


def main():
    print("Connecting to database ...")
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cursor:

            print(f"Loading {FURIGANA_JSON} ...")
            with open(FURIGANA_JSON, encoding="utf-8-sig") as f:
                furigana_data = json.load(f)
            total_entries = len(furigana_data)
            print(f"  Loaded {total_entries} entries.")

            BATCH_SIZE = 5000
            total_updated = 0
            batch_num = 0
            batch: list[tuple] = []

            print(f"  Processing in batches of {BATCH_SIZE} — building and sending as we go ...")

            for idx, entry in enumerate(furigana_data, start=1):
                text = entry.get("text", "").strip()
                reading = entry.get("reading", "").strip()
                furigana = entry.get("furigana")

                if not text or not reading or not furigana:
                    continue

                batch.append((json.dumps(furigana), text, reading))

                if len(batch) == BATCH_SIZE:
                    batch_num += 1
                    cursor.executemany(
                        "UPDATE vocab SET furigana = %s WHERE word = %s AND reading = %s",
                        batch,
                    )
                    conn.commit()
                    total_updated += cursor.rowcount
                    pct = idx / total_entries * 100
                    print(f"  Batch {batch_num} — {cursor.rowcount}/{BATCH_SIZE} matched — {idx}/{total_entries} entries processed ({pct:.1f}%) — {total_updated} vocab rows updated so far")
                    batch = []

            # flush final partial batch
            if batch:
                batch_num += 1
                cursor.executemany(
                    "UPDATE vocab SET furigana = %s WHERE word = %s AND reading = %s",
                    batch,
                )
                conn.commit()
                total_updated += cursor.rowcount
                print(f"  Batch {batch_num} (final) — {cursor.rowcount}/{len(batch)} matched — {total_updated} vocab rows updated so far")

            # Verification
            cursor.execute("SELECT COUNT(*) FROM vocab WHERE furigana IS NOT NULL")
            with_furigana = (cursor.fetchone() or (0,))[0]

            cursor.execute("SELECT COUNT(*) FROM vocab")
            total = (cursor.fetchone() or (0,))[0]

            print("── Summary ──────────────────────────────────────────────")
            print(f"  Total with furigana   : {with_furigana} / {total}")


if __name__ == "__main__":
    main()
