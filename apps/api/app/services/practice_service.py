# WHAT: Shared logic for the Practice tab's batch endpoints — resolving the
#       jlpt_level+scope filter into a concrete set of levels, splitting a
#       requested count across those levels for balanced/challenge
#       distribution, and parsing the exclude param.
# WHY:  /kanji/practice-batch, /vocab/practice-batch, and
#       /practice/sentence-cloze all share the exact same
#       jlpt_level/scope/distribution/count/exclude query contract — this
#       keeps that logic in one place instead of three.

from typing import Literal

from app.services.jlpt import JLPT_RANK

_LEVELS_BY_RANK = sorted(JLPT_RANK, key=lambda level: JLPT_RANK[level])  # N5..N1


def resolve_levels(jlpt_level: str, scope: Literal["exact", "and_below"]) -> list[str]:
    """The concrete set of JLPT levels to sample from, easiest first.

    "exact" -> just jlpt_level. "and_below" -> jlpt_level and every easier
    level (N5 is the floor, so N5 + and_below = N5 only)."""
    if scope == "exact":
        return [jlpt_level]
    target_rank = JLPT_RANK[jlpt_level]
    return [level for level in _LEVELS_BY_RANK if JLPT_RANK[level] <= target_rank]


def level_counts(
    levels: list[str], distribution: Literal["balanced", "challenge"], total: int
) -> dict[str, int]:
    """Split `total` across `levels`, returning a count per level that sums
    to `total` (Hamilton/largest-remainder apportionment).

    "balanced" weights every level equally. "challenge" weights each level
    by its JLPT_RANK (harder = higher rank = bigger share), so the hardest
    level(s) in range are clearly overrepresented vs. balanced mode. The
    exact weighting curve is an implementation choice — this is the
    simplest one that satisfies "clearly overrepresented."
    """
    if not levels:
        return {}

    weights = {level: (JLPT_RANK[level] if distribution == "challenge" else 1) for level in levels}
    weight_sum = sum(weights.values())

    raw = {level: total * weight / weight_sum for level, weight in weights.items()}
    counts = {level: int(value) for level, value in raw.items()}

    remainder = total - sum(counts.values())
    by_fraction_desc = sorted(levels, key=lambda level: raw[level] - counts[level], reverse=True)
    for level in by_fraction_desc[:remainder]:
        counts[level] += 1

    return counts


def parse_exclude(exclude: str | None) -> set[str]:
    """Comma-separated identifiers already seen this session -> a set of
    non-empty, whitespace-trimmed strings."""
    if not exclude:
        return set()
    return {item.strip() for item in exclude.split(",") if item.strip()}
