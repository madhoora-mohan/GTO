"""
Step 2.5 / Step 3.6 — "Soft" kanji/vocab checks.

"Soft" means: these functions only ever LOG what they find. They never
reject or modify a passage on their own — that decision belongs to the
caller, and the two tracks treat it very differently:

- Track A (this file's main use): log only, always. Wikipedia-sourced text
  legitimately uses kanji/words far outside any JLPT-tagged subset (this app
  imports the full ~10,384-character KANJIDIC2 table, not just JLPT kanji,
  so most of what shows up here will still resolve fine in the dictionary —
  only the genuinely rare/exotic characters get flagged). There is no
  rejection logic for Track A; flagged characters/words are purely for your
  own later spot-checking.

- Track B: the caller (generate_track_b.py) DOES use soft_kanji_check's
  result to reject a generated passage if too many kanji fall outside the
  target level's kanji set — because Track B passages are supposed to be
  tightly constrained to a JLPT level, unlike Track A's "whatever Wikipedia
  happens to contain."
"""

import re

from fugashi import Tagger

KANJI_PATTERN = re.compile(r"[一-龯]")

_tagger = Tagger()


def soft_kanji_check(text: str, known_kanji: set[str]) -> list[str]:
    """Kanji characters in text NOT found in known_kanji."""
    found = set(KANJI_PATTERN.findall(text))
    return sorted(found - known_kanji)


def soft_vocab_check(text: str, known_words: set[str]) -> list[str]:
    """Tokenized words (that contain at least one kanji) not found in known_words."""
    tokens = [word.surface for word in _tagger(text)]
    return [t for t in tokens if t not in known_words and KANJI_PATTERN.search(t)]
