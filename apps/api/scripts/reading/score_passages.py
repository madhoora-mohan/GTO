"""
Step 2.4 — Score passage difficulty with jReadability and map that score to
a JLPT level.

jReadability is an academic readability formula for Japanese text (Lee &
Hasebe). It outputs a single float on roughly a 1-6 scale: lower = harder
(advanced/academic text), higher = easier (beginner text). It was NOT built
with JLPT levels in mind, so LEVEL_BANDS below is our own estimate of which
score ranges correspond to which JLPT level — not an official mapping.

Used as a library (no __main__ batch runner here) — score_passage() is
called per-passage by generate_track_b.py (Step 3.7 cross-check) and by
whatever script seeds Track A content (Step 2.6), so every score gets
logged at the point of use, where the surrounding context (text, source) is
available too.
"""

from jreadability import compute_readability

# These thresholds are estimates based on the six-level jReadability scale
# (upper-advanced -> lower-elementary) cross-referenced against the JLPT
# five-level scale. They are NOT official. Treat passages near a boundary
# with suspicion — every score is logged by the caller so thresholds can be
# tuned later by spot-checking actual output against these bands.
LEVEL_BANDS = [
    ("N1", float("-inf"), 3.5),
    ("N2", 3.5, 4.5),
    ("N3", 4.5, 5.5),
    ("N4", 5.5, 6.5),
    ("N5", 6.5, float("inf")),
]


def score_to_jlpt_level(score: float) -> str:
    for level, low, high in LEVEL_BANDS:
        if low <= score < high:
            return level
    return "N1"  # fallback for anything below the lowest band


def score_passage(plain_text: str) -> tuple[float, str]:
    score = compute_readability(plain_text)
    level = score_to_jlpt_level(score)
    return round(score, 2), level
