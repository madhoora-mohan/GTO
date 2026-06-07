"""
apps/api/scripts/extract/populate_kanji_svg.py

Step 10 — uploads KanjiVG stroke-order SVGs to Cloudflare R2 and writes
kanji.stroke_order_svg_url.

Source: data/raw/kanjivg-20250816-all.zip (KanjiVG, CC BY-SA)
The zip already contains one canonical SVG per character at kanji/{codepoint}.svg
(zero-padded 5-digit lowercase hex Unicode codepoint), plus extra stroke-order
variants (e.g. 04e14-Kaisho.svg) that we don't need — we only use the base file.

For each kanji in the DB:
  1. Look up kanji/{codepoint}.svg in the zip (codepoint = f"{ord(character):05x}")
  2. Upload its bytes to R2 at svg/kanji/{codepoint}.svg
  3. Write the resulting public URL to kanji.stroke_order_svg_url

Run from apps/api/:
    uv run python scripts/extract/populate_kanji_svg.py

Requires in .env:
    DATABASE_URL, R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
    R2_BUCKET, R2_PUBLIC_URL
"""

import os
import zipfile
from pathlib import Path

import boto3
import psycopg
from dotenv import load_dotenv

load_dotenv()

# ── Config ───────────────────────────────────────────────────────────────────

DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
R2_PUBLIC_URL = os.environ["R2_PUBLIC_URL"]
BUCKET = os.environ["R2_BUCKET"]

KANJIVG_ZIP = Path("data/raw/kanjivg-20250816-all.zip")

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def upload_to_r2(codepoint: str, svg_bytes: bytes) -> str | None:
    """
    Uploads SVG bytes to R2 at svg/kanji/{codepoint}.svg
    Returns the public URL, or None on failure.
    """
    r2_key = f"svg/kanji/{codepoint}.svg"
    try:
        s3.put_object(
            Bucket=BUCKET,
            Key=r2_key,
            Body=svg_bytes,
            ContentType="image/svg+xml",
        )
        return f"{R2_PUBLIC_URL}/{r2_key}"
    except Exception as e:
        print(f"  UPLOAD ERROR {codepoint}: {e}")
        return None


# ── Main ─────────────────────────────────────────────────────────────────────

def populate_kanji_svg():
    with zipfile.ZipFile(KANJIVG_ZIP) as zf:
        names_in_zip = set(zf.namelist())

        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT character
                    FROM kanji
                    WHERE stroke_order_svg_url IS NULL
                    ORDER BY character
                """)
                characters = [row[0] for row in cur.fetchall()]

            print(f"  {len(characters)} kanji missing stroke_order_svg_url\n")

            uploaded = 0
            missing = 0
            failed = 0

            for character in characters:
                codepoint = f"{ord(character):05x}"
                zip_path = f"kanji/{codepoint}.svg"

                if zip_path not in names_in_zip:
                    print(f"  MISS  {character} ({codepoint})  (no {zip_path} in KanjiVG archive)")
                    missing += 1
                    continue

                svg_bytes = zf.read(zip_path)
                public_url = upload_to_r2(codepoint, svg_bytes)
                if not public_url:
                    failed += 1
                    continue

                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE kanji SET stroke_order_svg_url = %s WHERE character = %s",
                        (public_url, character)
                    )
                conn.commit()

                print(f"  OK    {character} ({codepoint})  → {public_url}")
                uploaded += 1

    print(f"\n  Done.")
    print(f"  Uploaded and written to DB: {uploaded}")
    print(f"  Not found in KanjiVG:       {missing}")
    print(f"  Upload failures:            {failed}")
    print()
    print("  Run verification query to confirm kanji.stroke_order_svg_url coverage:")
    print("    SELECT COUNT(*) total, COUNT(stroke_order_svg_url) has_svg")
    print("    FROM kanji;")


if __name__ == "__main__":
    populate_kanji_svg()
