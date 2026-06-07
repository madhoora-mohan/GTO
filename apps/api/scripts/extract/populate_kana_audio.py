"""
apps/api/scripts/extract/populate_kana_audio.py

Stage 2 of 2 for kana audio: uploads the .mp3 files produced by
extract_kana_audio.py (stored locally in data/raw/audio/kana/) to Cloudflare R2,
then writes the resulting public URL to kana.audio_url.

Hiragana and katakana share the same sound for each mora — so one uploaded
file's URL is written to BOTH the hiragana and katakana row for that romaji.
e.g. the URL for Ja-ki.oga is written to both き and キ.

Run from apps/api/, AFTER extract_kana_audio.py has populated data/raw/audio/kana/:
    uv run python scripts/extract/populate_kana_audio.py

Requires in .env:
    DATABASE_URL, R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
    R2_BUCKET, R2_PUBLIC_URL
"""

import os
from pathlib import Path

import boto3
import psycopg
from dotenv import load_dotenv

load_dotenv()

# ── Config ───────────────────────────────────────────────────────────────────

DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
R2_PUBLIC_URL = os.environ["R2_PUBLIC_URL"]
BUCKET = os.environ["R2_BUCKET"]

AUDIO_DIR = Path("data/raw/audio/kana")

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def upload_to_r2(romaji: str, audio_bytes: bytes) -> str | None:
    """
    Uploads audio bytes to R2 at audio/kana/{romaji}.oga
    Returns the public URL, or None on failure.
    """
    r2_key = f"audio/kana/{romaji}.mp3"
    try:
        s3.put_object(
            Bucket=BUCKET,
            Key=r2_key,
            Body=audio_bytes,
            ContentType="audio/mpeg",
        )
        return f"{R2_PUBLIC_URL}/{r2_key}"
    except Exception as e:
        print(f"  UPLOAD ERROR {romaji}: {e}")
        return None


# ── Main ─────────────────────────────────────────────────────────────────────

def populate_kana_audio():
    files = sorted(AUDIO_DIR.glob("*.mp3"))
    print(f"  {len(files)} local audio files found in {AUDIO_DIR}/\n")

    uploaded = 0
    failed = 0

    with psycopg.connect(DB_URL) as conn:
        for path in files:
            romaji = path.stem  # "ki.mp3" -> "ki"

            public_url = upload_to_r2(romaji, path.read_bytes())
            if not public_url:
                failed += 1
                continue

            # Write the URL to ALL kana rows that share this romaji (hiragana + katakana)
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE kana SET audio_url = %s WHERE romaji = %s",
                    (public_url, romaji)
                )
            conn.commit()

            print(f"  OK    {romaji}  → {public_url}")
            uploaded += 1

    print(f"\n  Done.")
    print(f"  Uploaded and written to DB: {uploaded}")
    print(f"  Failed:                     {failed}")
    print()
    print("  Run verification query to confirm kana.audio_url coverage:")
    print("    SELECT COUNT(*) total, COUNT(audio_url) has_audio")
    print("    FROM kana;")
    print("  Expected: total=214, has_audio should be close to 214.")


if __name__ == "__main__":
    populate_kana_audio()
