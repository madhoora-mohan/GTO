# WHAT: Generates a solved, interlocking crossword grid for
#       GET /vocab/crossword — selects a JLPT-filtered pool of vocab words,
#       greedily places them so they intersect at shared kana, then builds
#       the cell/word/decoy-kana response shape.
# WHY:  Unlike the other Practice endpoints, the number of words that fit
#       isn't requested directly — it's a property of how well the
#       candidate pool happens to interlock. The placement algorithm
#       (_build_grid) is pure/sync so it's cheap to unit test against
#       synthetic word lists without a DB.

import random
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kana import Kana
from app.models.vocab import Vocab
from app.services.practice_service import level_counts, resolve_levels

# Minimum interlocked words for a grid to be considered usable. Below this,
# the puzzle would feel sparse/trivial, so we report insufficient=true
# instead (an expected outcome of a narrow JLPT filter, not an error).
_MIN_WORDS = 3

# How many candidate words to pull from the DB before attempting placement.
# Oversampled well beyond _MIN_WORDS since most candidates won't find a
# valid intersection and get skipped.
_CANDIDATE_POOL_SIZE = 50

Direction = Literal["across", "down"]


@dataclass
class _Candidate:
    id: str
    answer: str  # kana reading — what actually gets placed in the grid
    clue: str


@dataclass
class _PlacedWord:
    id: int
    answer: str
    clue: str
    row: int
    col: int
    direction: Direction


def _can_place(
    occupied: dict[tuple[int, int], str], answer: str, row: int, col: int, direction: Direction
) -> bool:
    """Whether `answer` can be placed at (row, col) in `direction` without
    conflicting with already-placed letters, and with at least one real
    intersection (this is only called for the 2nd+ word)."""
    delta = (0, 1) if direction == "across" else (1, 0)
    perp = (1, 0) if direction == "across" else (0, 1)

    before = (row - delta[0], col - delta[1])
    after = (row + delta[0] * len(answer), col + delta[1] * len(answer))
    if before in occupied or after in occupied:
        return False

    crosses = 0
    for i, ch in enumerate(answer):
        cell = (row + delta[0] * i, col + delta[1] * i)
        existing = occupied.get(cell)
        if existing is not None:
            if existing != ch:
                return False
            crosses += 1
        else:
            # Cell is empty here — but if its perpendicular neighbor is
            # occupied, placing this letter would make this word visually
            # run flush against an unrelated word with no actual crossing.
            n1 = (cell[0] + perp[0], cell[1] + perp[1])
            n2 = (cell[0] - perp[0], cell[1] - perp[1])
            if n1 in occupied or n2 in occupied:
                return False

    return crosses > 0


def _find_placement(
    occupied: dict[tuple[int, int], str], answer: str
) -> tuple[Direction, int, int] | None:
    """A random valid (direction, row, col) for `answer` against the
    already-placed letters, or None if no intersection works."""
    attempts: list[tuple[Direction, int, int]] = []
    for i, ch in enumerate(answer):
        for (r, c), existing_ch in occupied.items():
            if existing_ch != ch:
                continue
            attempts.append(("across", r, c - i))
            attempts.append(("down", r - i, c))

    random.shuffle(attempts)
    for direction, row, col in attempts:
        if _can_place(occupied, answer, row, col, direction):
            return direction, row, col
    return None


_BuildResult = tuple[list[_PlacedWord], dict[tuple[int, int], str], dict[tuple[int, int], set[int]]]


def _attempt_build(pool: list[_Candidate], seed_index: int) -> _BuildResult:
    """Greedily place `pool[seed_index]` first, then try every other
    candidate against whatever's already on the board. Returns
    (placed words, occupied cells, cell -> word ids) — placed has length 1
    if nothing else could attach to the seed."""
    occupied: dict[tuple[int, int], str] = {}
    cell_word_ids: dict[tuple[int, int], set[int]] = {}
    placed: list[_PlacedWord] = []

    def _place(candidate: _Candidate, word_id: int, row: int, col: int, direction: Direction) -> None:
        delta = (0, 1) if direction == "across" else (1, 0)
        for i, ch in enumerate(candidate.answer):
            cell = (row + delta[0] * i, col + delta[1] * i)
            occupied[cell] = ch
            cell_word_ids.setdefault(cell, set()).add(word_id)
        placed.append(
            _PlacedWord(
                id=word_id, answer=candidate.answer, clue=candidate.clue,
                row=row, col=col, direction=direction,
            )
        )

    seed = pool[seed_index]
    rest = pool[:seed_index] + pool[seed_index + 1 :]
    _place(seed, 0, 0, 0, "across")

    next_id = 1
    for candidate in rest:
        placement = _find_placement(occupied, candidate.answer)
        if placement is None:
            continue
        direction, row, col = placement
        _place(candidate, next_id, row, col, direction)
        next_id += 1

    return placed, occupied, cell_word_ids


def _build_grid(candidates: list[_Candidate]) -> dict | None:
    """Try every candidate as the seed word and keep whichever attempt
    interlocks the most words — a single seed (e.g. the longest word) might
    happen to share no letters with anything else, which would otherwise
    sink an otherwise-good batch. Returns None if no seed reaches
    _MIN_WORDS."""
    pool = [c for c in candidates if len(c.answer) >= 2]
    if len(pool) < _MIN_WORDS:
        return None

    best: _BuildResult | None = None
    for seed_index in range(len(pool)):
        placed, occupied, cell_word_ids = _attempt_build(pool, seed_index)
        if len(placed) < _MIN_WORDS:
            continue
        if best is None or len(placed) > len(best[0]):
            best = (placed, occupied, cell_word_ids)
        if best is not None and len(best[0]) == len(pool):
            break  # can't beat placing every candidate

    if best is None:
        return None
    placed, occupied, cell_word_ids = best

    rows = [cell[0] for cell in occupied]
    cols = [cell[1] for cell in occupied]
    min_row, min_col = min(rows), min(cols)
    height, width = max(rows) - min_row + 1, max(cols) - min_col + 1

    cells = []
    for r in range(height):
        for c in range(width):
            key = (r + min_row, c + min_col)
            if key in occupied:
                cells.append({
                    "row": r, "col": c, "blocked": False,
                    "letter": occupied[key],
                    "word_ids": sorted(cell_word_ids[key]),
                })
            else:
                cells.append({"row": r, "col": c, "blocked": True, "letter": None, "word_ids": []})

    words = [
        {
            "id": w.id, "word": w.answer, "clue": w.clue,
            "row": w.row - min_row, "col": w.col - min_col,
            "direction": w.direction,
        }
        for w in placed
    ]

    used_kana = {ch for w in placed for ch in w.answer}

    return {
        "insufficient": False,
        "width": width,
        "height": height,
        "cells": cells,
        "words": words,
        "_used_kana": used_kana,  # stripped before the response is sent
    }


async def _get_candidates(
    db: AsyncSession,
    jlpt_level: Literal["N1", "N2", "N3", "N4", "N5"],
    scope: Literal["exact", "and_below"],
    distribution: Literal["balanced", "challenge"],
) -> list[_Candidate]:
    levels = resolve_levels(jlpt_level, scope)
    counts = level_counts(levels, distribution, _CANDIDATE_POOL_SIZE)

    rows: list[Vocab] = []
    for level, n in counts.items():
        if n <= 0:
            continue
        stmt = select(Vocab).where(Vocab.jlpt == level).order_by(func.random()).limit(n)
        rows.extend((await db.execute(stmt)).scalars().all())

    candidates: list[_Candidate] = []
    seen_readings: set[str] = set()
    for vocab in rows:
        if vocab.reading in seen_readings:
            continue
        definitions = (vocab.meanings[0].get("definitions") if vocab.meanings else None) or []
        if not definitions:
            continue
        seen_readings.add(vocab.reading)
        candidates.append(_Candidate(id=vocab.id, answer=vocab.reading, clue=definitions[0]))

    return candidates


async def _get_decoy_kana(db: AsyncSession, used_kana: set[str]) -> list[str]:
    count = max(8, min(len(used_kana), 20))
    stmt = (
        select(Kana.character)
        .where(Kana.character.notin_(used_kana))
        .order_by(func.random())
        .limit(count)
    )
    return list((await db.execute(stmt)).scalars().all())


_EMPTY_GRID = {
    "insufficient": True,
    "width": 0,
    "height": 0,
    "cells": [],
    "words": [],
    "decoy_kana": [],
}


async def get_crossword(
    db: AsyncSession,
    jlpt_level: Literal["N1", "N2", "N3", "N4", "N5"],
    scope: Literal["exact", "and_below"],
    distribution: Literal["balanced", "challenge"],
) -> dict:
    """A solved, interlocking crossword grid for this JLPT filter, or
    insufficient=true if fewer than _MIN_WORDS could be interlocked."""
    candidates = await _get_candidates(db, jlpt_level, scope, distribution)
    grid = _build_grid(candidates)
    if grid is None:
        return _EMPTY_GRID

    used_kana = grid.pop("_used_kana")
    grid["decoy_kana"] = await _get_decoy_kana(db, used_kana)
    return grid
