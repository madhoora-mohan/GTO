"""
apps/api/scripts/extract/extract_kana_audio.py

Downloads Japanese kana pronunciation audio from Wikimedia Commons and stores
the files locally under data/raw/audio/kana/ — same pattern as the KanjiVG
SVGs (downloaded first, uploaded to R2 later once credentials are ready).

Source: The canonical "Ja-{romaji}.oga" files used by Wikipedia's own kana articles.
License: CC BY-SA — see each file's Commons page for exact attribution.

Hiragana and katakana share the same sound for each mora — so one audio file
covers both scripts. e.g. Ja-ki.oga covers both き and キ. We only need to
download one file per unique romaji.

Commons serves these as .oga (Ogg Vorbis). We convert each to .mp3 (via the
system `ffmpeg` binary) before storing, so the files we keep/upload are in the
format the app actually wants to serve.

Expected: ~57 unique sound files saved locally.

This is stage 1 of 2:
  1. extract_kana_audio.py   ← (this script) download + convert to data/raw/audio/kana/*.mp3
  2. (later) populate_kana_audio.py — upload to R2 and write kana.audio_url,
     once R2 credentials are configured in .env.

Run from apps/api/:
    uv run python scripts/extract/extract_kana_audio.py

Requires in .env:
    DATABASE_URL   (used only to read the distinct romaji list from `kana`)

Requires `ffmpeg` on PATH (used to convert .oga -> .mp3).
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import psycopg
from dotenv import load_dotenv

load_dotenv()

# ── Config ───────────────────────────────────────────────────────────────────

DB_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

AUDIO_DIR = Path("data/raw/audio/kana")

# Commons file names for these recordings are NOT a single predictable
# pattern: e.g. "Ja-Ka.oga", "Ja-A.oga", "Ja-ka.ogg" all exist with different
# capitalization and extensions. So instead of guessing a URL directly, we ask
# the MediaWiki API which of our candidate titles actually exists and get its
# real file URL back (via prop=imageinfo).
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "JapaneseLearnApp/1.0 (kana audio seeding)"


# ── Helpers ──────────────────────────────────────────────────────────────────

def convert_oga_to_mp3(oga_bytes: bytes, dest: Path) -> bool:
    """
    Converts raw .oga bytes to an .mp3 file at `dest` using the system ffmpeg
    binary. Returns True on success, False on failure.
    """
    with tempfile.NamedTemporaryFile(suffix=".oga") as tmp:
        tmp.write(oga_bytes)
        tmp.flush()
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-i", tmp.name,
                    "-codec:a", "libmp3lame", "-qscale:a", "2",
                    str(dest),
                ],
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"  CONVERT ERROR {dest.stem}: {e}")
            return False


def get_with_retry(url: str, *, params: dict | None = None, max_retries: int = 8) -> httpx.Response:
    """
    GETs a URL, retrying with backoff on 429 (Too Many Requests).

    Wikimedia's Retry-After header (often "10") is shorter than its actual
    rate-limit window for anonymous traffic, so a flat retry-after wait keeps
    tripping the limit again. We take the larger of the header value and a
    growing floor (30, 60, 90, 120... seconds) so retries actually clear the
    window.
    """
    for attempt in range(max_retries):
        r = httpx.get(
            url, params=params, timeout=15,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        if r.status_code != 429:
            return r

        header_wait = int(r.headers.get("retry-after", 0))
        floor_wait = 30 * (attempt + 1)
        wait = max(header_wait, floor_wait)
        print(f"  429 rate limited — waiting {wait}s before retry "
              f"({attempt + 1}/{max_retries})")
        time.sleep(wait)

    return r


def find_commons_file_url(romaji: str) -> str | None:
    """
    Looks up the real Commons file URL for a kana sound.

    Capitalization and extension are inconsistent on Commons (Ja-Ka.oga,
    Ja-A.oga, Ja-ka.ogg all exist as real, differently-cased/extensioned
    files), so we ask the MediaWiki API about a batch of candidate titles
    and return the URL of whichever one actually exists.
    """
    candidates = [
        f"Ja-{form}.{ext}"
        for form in (romaji, romaji.capitalize(), romaji.upper())
        for ext in ("oga", "ogg")
    ]
    titles = "|".join(f"File:{c}" for c in candidates)

    try:
        r = get_with_retry(
            COMMONS_API,
            params={
                "action": "query",
                "titles": titles,
                "prop": "imageinfo",
                "iiprop": "url",
                "format": "json",
            },
        )
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            imageinfo = page.get("imageinfo")
            if imageinfo:
                return imageinfo[0]["url"]
        return None
    except Exception as e:
        print(f"  LOOKUP ERROR {romaji}: {e}")
        return None


def download_commons_audio(romaji: str) -> bytes | None:
    """
    Finds and downloads the Commons audio file for a kana sound.
    Returns raw bytes on success, None if no matching file exists or download fails.
    """
    url = find_commons_file_url(romaji)
    if not url:
        return None

    try:
        r = get_with_retry(url)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"  DOWNLOAD ERROR {romaji}: {e}")
        return None


# ── Main ─────────────────────────────────────────────────────────────────────

def extract_kana_audio():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            # Distinct romaji values — one download covers both the hiragana
            # and katakana row for that sound.
            cur.execute("SELECT DISTINCT romaji FROM kana ORDER BY romaji")
            all_romaji = [row[0] for row in cur.fetchall()]

    print(f"  {len(all_romaji)} unique sounds to fetch from Wikimedia Commons")
    print(f"  saving to {AUDIO_DIR}/\n")

    downloaded = 0
    skipped = 0
    missing = 0

    for romaji in all_romaji:
        dest = AUDIO_DIR / f"{romaji}.mp3"
        if dest.exists():
            skipped += 1
            continue

        audio_bytes = download_commons_audio(romaji)

        if not audio_bytes:
            print(f"  MISS  {romaji}  (no matching Ja-{romaji} audio file on Commons)")
            missing += 1
            time.sleep(3)
            continue

        if not convert_oga_to_mp3(audio_bytes, dest):
            missing += 1
            time.sleep(3)
            continue

        print(f"  OK    {romaji}  → {dest}")
        downloaded += 1
        time.sleep(3)  # polite rate limit for Wikimedia — avoids 429s

    print(f"\n  Done.")
    print(f"  Downloaded:           {downloaded}")
    print(f"  Already present:      {skipped}")
    print(f"  Not found on Commons: {missing}")
    print()
    print("  Next: once R2 credentials are configured in .env, run the")
    print("  populate step to upload these files to R2 and write kana.audio_url.")


if __name__ == "__main__":
    extract_kana_audio()
