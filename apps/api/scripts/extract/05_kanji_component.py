"""
Step 5 — Extract KRADFILE → `kanji_component` table.

Run from apps/api/:
    uv run python scripts/extract/05_kanji_component.py

Source: data/raw/kradfile (EUC-JP encoded — NOT UTF-8)

KRADFILE maps each kanji to the visual components it is made of.
Each line looks like:
    新 : 亠 木 斤 立
meaning "新 is composed of 亠, 木, 斤, 立" in that order.

We insert one row per (kanji, component) pair with the position (1-based order).

Prerequisites:
- Step 3 must have run: components table must be populated (we look up component.id)
- Step 4 must have run: kanji table must be populated (foreign key constraint)

Rows where the kanji or component is not in our DB are silently skipped
(KRADFILE covers more kanji than our KANJIDIC2 import, and that's fine).

Script is idempotent: ON CONFLICT DO NOTHING.
"""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

RAW = Path("data/raw")
KRADFILE = RAW / "kradfile"


def main():
    print("Connecting to database ...")
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cursor:

            # Build a lookup: component character → component.id
            # e.g. {'木': 12, '斤': 34, '立': 56, ...}
            # We need the integer id to insert into kanji_component.component_id.
            cursor.execute("SELECT character, id FROM components")
            component_lookup = {char: cid for char, cid in cursor.fetchall()}
            print(f"  Loaded {len(component_lookup)} components into lookup.")

            # Build a set of all kanji characters in our DB.
            # KRADFILE has more kanji than we imported from KANJIDIC2, so we
            # skip any kanji that isn't in our table to avoid FK violations.
            cursor.execute("SELECT character FROM kanji")
            known_kanji = {r[0] for r in cursor.fetchall()}
            print(f"  Loaded {len(known_kanji)} kanji into lookup.")

            print(f"  Parsing {KRADFILE} ...")

            rows = []
            skipped_kanji = 0
            skipped_component = 0

            # KRADFILE is EUC-JP encoded — passing the wrong encoding produces garbage.
            with open(KRADFILE, encoding="euc-jp") as f:
                for line in f:
                    # Skip comment lines (start with #) and blank lines
                    if line.startswith("#") or not line.strip():
                        continue

                    # Each line: "新 : 亠 木 斤 立"
                    # Split on whitespace — first token is the kanji,
                    # second is ':', remainder are the components in order.
                    parts = line.strip().split()
                    if len(parts) < 3:
                        continue

                    kanji_char = parts[0]
                    # parts[1] is ':', parts[2:] are the component characters
                    components = parts[2:]

                    if kanji_char not in known_kanji:
                        skipped_kanji += 1
                        continue

                    for position, component_char in enumerate(components, start=1):
                        if component_char not in component_lookup:
                            skipped_component += 1
                            continue

                        component_id = component_lookup[component_char]
                        rows.append((kanji_char, component_id, position))

            print(f"  Parsed {len(rows)} (kanji, component) pairs.")
            print(f"  Skipped {skipped_kanji} kanji not in our DB.")
            print(f"  Skipped {skipped_component} component references not in our lookup.")
            print(f"  Inserting ...")

            cursor.executemany(
                """
                INSERT INTO kanji_component (kanji_char, component_id, position)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                rows,
            )
            conn.commit()

            # Verification
            cursor.execute("SELECT COUNT(*) FROM kanji_component")
            total = (cursor.fetchone() or (0,))[0]

            print("── Summary ──────────────────────────────────────────────")
            print(f"  Total rows in kanji_component : {total}")


if __name__ == "__main__":
    main()
