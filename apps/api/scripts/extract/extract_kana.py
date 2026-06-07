"""
Step 11 — Extract Japanese-JSON → `kana` table (all 208+ kana characters).

Run from apps/api/:
    uv run scripts/extract/extract_kana.py

Source: data/raw/japanese-json/kana.json (merwan7/Japanese-JSON, MIT license)
This replaces the originally-planned KanaAPI source — that JSON only had 92
entries (46 hiragana + 46 katakana, base forms only) with an empty `category`
field, and didn't cover dakuten/handakuten/yōon at all. Japanese-JSON has the
full set. See docs/kana-source-swap-intervention.md for the full story.

What the source data looks like — a nested object, NOT a flat list:
    {
      "k": {
        "a":  { "Seion":  {"Katakana": "カ", "Hiragana": "か", "Romaji": "ka"},
                "Dakuon": {"Katakana": "ガ", "Hiragana": "が", "Romaji": "ga"} },
        "ya": { "Seion":  {"Katakana": "キャ", "Hiragana": "きゃ", "Romaji": "kya"} }
      },
      ...
    }
  - Top-level key   = consonant group ("-" = pure vowels, "*" = ん/ン)
  - Second-level    = vowel (a/i/u/e/o, or ya/yu/yo for yōon compounds)
  - Third-level key = sound type: Seion (base), Dakuon (voiced), Handakuon (semi-voiced)

Each JSON entry describes ONE hiragana+katakana pair, so it produces TWO rows
in our `kana` table — one row of type='hiragana', one of type='katakana' —
each pointing at the other via katakana_equivalent / hiragana_equivalent.

`row` and `col` (the kana chart grid position) aren't in the source data —
we derive them from romaji + category below.

Known data bug in the source (verified by hand — see docs/kana-source-swap-intervention.md):
the ぢょ (Dakuon, t-row, "yo") entry has Katakana "ヂュ", which is actually the
katakana for ぢゅ (a duplicate / copy-paste typo upstream — it should be "ヂョ").
We patch it below before inserting; otherwise we'd get a duplicate `character`
value, and the real ヂョ character would never make it into the table.

Run from apps/api/. Requires DATABASE_URL in .env.
"""

import json
import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
KANA_JSON_PATH = "data/raw/japanese-json/kana.json"

# ── Known upstream typo — see module docstring ───────────────────────────────
# (consonant_key, vowel_key, sound_type) -> corrected Katakana value
KATAKANA_PATCHES = {
    ("t", "yo", "Dakuon"): "ヂョ",
}


# ── row/col derivation ────────────────────────────────────────────────────────
# row and col represent the character's position on the standard kana chart.
# They aren't in the source JSON — we derive them from romaji + category.

VOWELS = {"a", "i", "u", "e", "o"}

# Maps a romaji consonant prefix to the "base" chart row it belongs under.
# e.g. "sh" (as in "shi") sits in the same chart row as "s" (sa/su/se/so).
ROW_MAP = {
    "sh": "s", "ch": "t", "ts": "t", "hy": "h",
    "gy": "g", "ky": "k", "ny": "n", "my": "m",
    "ry": "r", "by": "b", "py": "p", "zy": "z",
    "jy": "z", "j": "z", "f": "h", "w": "w",
}


def derive_row_col(romaji: str, category: str) -> tuple[str | None, str | None]:
    """
    Work out the kana chart (row, col) position from romaji + category.

    - yōon (compound, e.g. きゃ): no single chart cell — both NULL
    - ん / ン: standalone nasal, has a row but no vowel column
    - pure vowels (a/i/u/e/o): live in their own "vowel" row
    - everything else: last romaji letter = vowel column,
                        the rest = consonant, normalised to its base row
    """
    if category == "yoon":
        return None, None
    if romaji == "n":
        return "n", None
    if romaji in VOWELS:
        return "vowel", romaji

    col = romaji[-1]
    prefix = romaji[:-1]
    row = ROW_MAP.get(prefix, prefix)
    return row, col


# ── category mapping ──────────────────────────────────────────────────────────

def get_category(sound_type: str, vowel_key: str) -> str:
    """
    Map the JSON's sound-type key to our DB `category` value.

    Yōon is detected by the *vowel* key (ya/yu/yo) — it overrides sound type,
    because a compound like ぎゃ is "yōon" in our chart, not "dakuten".
    """
    if vowel_key in ("ya", "yu", "yo"):
        return "yoon"
    return {"Seion": "base", "Dakuon": "dakuten", "Handakuon": "handakuten"}[sound_type]


# ── main extraction ───────────────────────────────────────────────────────────

def extract_kana():
    with open(KANA_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    rows = []  # one dict per `kana` table row — two per JSON entry (hiragana + katakana)

    for consonant_key, vowel_map in data.items():
        for vowel_key, type_map in vowel_map.items():
            for sound_type, entry in type_map.items():
                hiragana_char = entry.get("Hiragana")
                katakana_char = entry.get("Katakana")
                romaji = entry.get("Romaji", "")

                # Apply the upstream-typo patch if this entry is the known bad one.
                patch_key = (consonant_key, vowel_key, sound_type)
                if patch_key in KATAKANA_PATCHES:
                    fixed = KATAKANA_PATCHES[patch_key]
                    print(f"  PATCH  {consonant_key}/{vowel_key}/{sound_type}: "
                          f"katakana '{katakana_char}' -> '{fixed}' (upstream typo)")
                    katakana_char = fixed

                if not hiragana_char or not katakana_char:
                    print(f"  SKIP  missing char: {consonant_key}/{vowel_key}/{sound_type}")
                    continue

                category = get_category(sound_type, vowel_key)
                row, col = derive_row_col(romaji, category)

                rows.append({
                    "character": hiragana_char,
                    "romaji": romaji,
                    "type": "hiragana",
                    "category": category,
                    "row": row,
                    "col": col,
                    "katakana_equivalent": katakana_char,
                    "hiragana_equivalent": None,
                })
                rows.append({
                    "character": katakana_char,
                    "romaji": romaji,
                    "type": "katakana",
                    "category": category,
                    "row": row,
                    "col": col,
                    "katakana_equivalent": None,
                    "hiragana_equivalent": hiragana_char,
                })

    print(f"\nParsed {len(rows)} kana rows from JSON ({len(rows) // 2} hiragana+katakana pairs)")

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute("""
                    INSERT INTO kana
                        (character, romaji, type, category, row, col,
                         katakana_equivalent, hiragana_equivalent)
                    VALUES
                        (%(character)s, %(romaji)s, %(type)s, %(category)s,
                         %(row)s, %(col)s, %(katakana_equivalent)s, %(hiragana_equivalent)s)
                    ON CONFLICT (character) DO UPDATE SET
                        romaji              = EXCLUDED.romaji,
                        type                = EXCLUDED.type,
                        category            = EXCLUDED.category,
                        row                 = EXCLUDED.row,
                        col                 = EXCLUDED.col,
                        katakana_equivalent = EXCLUDED.katakana_equivalent,
                        hiragana_equivalent = EXCLUDED.hiragana_equivalent
                """, r)
        conn.commit()

    print(f"Done. {len(rows)} rows inserted/updated in the kana table.")
    print()
    print("Note: this source has no ゐ/ゑ (obsolete kana) — unlike the originally")
    print("planned KanaAPI source, no manual ゐ/ゑ row/col patches are needed here.")
    print("Run the verification queries in docs/kana-source-swap-intervention.md §4")
    print("(updated expected total: 214 rows / 107 pairs — see that doc for why).")


if __name__ == "__main__":
    extract_kana()
