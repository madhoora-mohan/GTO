"""
Step 2.3 (Aozora half) — Parse selected Aozora Bunko HTML files into plain
text + furigana segments.

Run from apps/api/ (after aozora_selected.txt has been filled in manually —
see the bottom of download_sources.py's output, and the docstring in this
file's `main()` for what that file should contain):

    uv run scripts/reading/normalize_aozora.py

IMPORTANT — this deviates from the handoff doc's original plan:
The handoff doc assumed Aozora's plain-text release format, which marks
furigana with full-width pipes and brackets like ｜化｜物《ばけもの》. That
format does NOT exist in the actual git clone of the aozorabunko repo —
what's actually there (cards/*/files/*.html) is generated XHTML using
semantic <ruby><rb>base</rb><rt>reading</rt></ruby> tags, encoded in
Shift_JIS. This is actually easier and more reliable to parse than the
bracket-regex the doc proposed (no regex guessing about ambiguous bracket
nesting), so this file parses the real HTML structure instead. Confirmed by
manually opening several of the selected files before writing this parser
(per the doc's own instruction to inspect real files before trusting any
particular parsing approach).

HTML structure per file (all confirmed by manual inspection):
- <h1 class="title">...</h1> / <h2 class="author">...</h2> — metadata.
- <div class="main_text"> ... </div> — the actual story body. Paragraphs
  are separated by <br />, indented blocks are wrapped in
  <div class="jisage_N">, and furigana is <ruby><rb>BASE</rb><rp>(</rp>
  <rt>READING</rt><rp>)</rp></ruby>.
- <div class="bibliographical_information"> ... — the "底本：" (source
  edition) footer, immediately after main_text. Cut here.
- <div class="notation_notes"> ... — a notes-about-this-file footer. Also
  excluded (it always comes after bibliographical_information, so cutting
  at bibliographical_information's start already excludes it too).

Gaiji (rare characters not in standard Shift_JIS, rendered as <img> glyphs
instead of real text) make a file unusable for our purposes — there's no
clean way to put "a tiny image of a character" into passage_text. Any file
containing such an image is skipped entirely rather than guessed at.
"""

import html
import json
import re
import unicodedata
from pathlib import Path

RAW_DIR = Path("data/raw/reading")
AOZORA_DIR = RAW_DIR / "aozora_raw"
SELECTED_LIST = RAW_DIR / "aozora_selected.txt"

TITLE_RE = re.compile(rb'<h1 class="title">(.*?)</h1>', re.DOTALL)
AUTHOR_RE = re.compile(rb'<h2 class="author">(.*?)</h2>', re.DOTALL)
TAG_STRIP_RE = re.compile(rb"<[^>]+>")

MAIN_TEXT_START_RE = re.compile(rb'<div class="main_text">')
FOOTER_START_RE = re.compile(rb'<div class="bibliographical_information">')

# Either a full ruby block (captures base text + reading) or any other
# single HTML tag (to be dropped, except <br /> which becomes a newline).
TOKEN_RE = re.compile(
    rb"<ruby><rb>(?P<base>.*?)</rb><rp>.*?</rp><rt>(?P<reading>.*?)</rt><rp>.*?</rp></ruby>"
    rb"|<br\s*/?>"
    rb"|<[^>]+>",
    re.DOTALL,
)


def _decode(raw_bytes: bytes) -> str:
    return html.unescape(raw_bytes.decode("shift_jis", errors="replace"))


def parse_aozora_html(path: Path) -> dict | None:
    """Returns {title, author, passage_text, furigana_segments} or None if
    this file should be skipped (no recognizable main_text, or contains
    gaiji images we can't render as plain text)."""
    raw = path.read_bytes()

    title_m = TITLE_RE.search(raw)
    author_m = AUTHOR_RE.search(raw)
    if not title_m:
        return None
    title = _decode(TAG_STRIP_RE.sub(b"", title_m.group(1))).strip()
    author = _decode(TAG_STRIP_RE.sub(b"", author_m.group(1))).strip() if author_m else ""

    start_m = MAIN_TEXT_START_RE.search(raw)
    if not start_m:
        return None
    end_m = FOOTER_START_RE.search(raw, start_m.end())
    body = raw[start_m.end(): end_m.start() if end_m else len(raw)]

    if b"<img" in body:
        return None  # gaiji (or any other embedded image) — skip, can't render as text

    # Build raw segments first — ruby segments (have "rt") stay separate,
    # everything else (plain text, <br/> newlines) gets merged into one
    # running plain-text segment so multiple consecutive <br/> tags collapse
    # into a single "\n" rather than three separate one-newline segments.
    raw_segments: list[dict] = []
    pending_plain = ""

    def flush_plain() -> None:
        nonlocal pending_plain
        if pending_plain:
            raw_segments.append({"ruby": pending_plain})
            pending_plain = ""

    pos = 0
    for m in TOKEN_RE.finditer(body):
        if m.start() > pos:
            pending_plain += _decode(body[pos:m.start()])

        if m.group("base") is not None:
            flush_plain()
            raw_segments.append({"ruby": _decode(m.group("base")), "rt": _decode(m.group("reading"))})
        elif m.group(0).strip().startswith(b"<br"):
            pending_plain += "\n"
        # else: some other tag (div open/close, <a>, <hr> etc.) — dropped

        pos = m.end()
    pending_plain += _decode(body[pos:])
    flush_plain()

    # NFKC-normalize and collapse repeated blank lines within each plain
    # segment, so a segment's text is identical to what passage_text would
    # show for that span — no separate, divergent cleanup of passage_text.
    segments = []
    for seg in raw_segments:
        if "rt" in seg:
            segments.append(seg)
        else:
            text = re.sub(r"\n{2,}", "\n", unicodedata.normalize("NFKC", seg["ruby"]))
            if text:
                segments.append({"ruby": text})

    # Trim leading/trailing whitespace-only plain segments, and lstrip/rstrip
    # the new boundary segments, so concatenating furigana_segments produces
    # exactly passage_text (no leading/trailing blank lines either side).
    while segments and "rt" not in segments[0] and not segments[0]["ruby"].strip():
        segments.pop(0)
    while segments and "rt" not in segments[-1] and not segments[-1]["ruby"].strip():
        segments.pop()
    if segments and "rt" not in segments[0]:
        segments[0]["ruby"] = segments[0]["ruby"].lstrip()
    if segments and "rt" not in segments[-1]:
        segments[-1]["ruby"] = segments[-1]["ruby"].rstrip()

    passage_text = "".join(s["ruby"] for s in segments)

    if not passage_text:
        return None

    return {
        "title": title,
        "author": author,
        "passage_text": passage_text,
        "furigana_segments": segments,
    }


def main() -> None:
    if not SELECTED_LIST.exists():
        raise SystemExit(
            f"{SELECTED_LIST} not found. Manually curate 30-50 short Aozora "
            f"works first (see data/raw/reading/aozora_index.json for "
            f"title/author/byte_size of every available work) and list "
            f"their `path` values there, one per line."
        )

    paths = [
        Path(line.strip()) for line in SELECTED_LIST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    accepted = []
    for path in paths:
        result = parse_aozora_html(path)
        if result is None:
            print(f"  [SKIP] could not parse or contains gaiji: {path}")
            continue
        print(f"  [OK] {result['title']} ({result['author']}) — {len(result['passage_text'])} chars")
        accepted.append(result)

    out_path = RAW_DIR / "normalized_aozora.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(accepted, f, ensure_ascii=False, indent=2)
    print(f"\n{len(accepted)}/{len(paths)} works parsed successfully -> {out_path}")


if __name__ == "__main__":
    main()
