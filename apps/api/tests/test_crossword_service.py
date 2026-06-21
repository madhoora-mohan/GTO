from app.services.crossword_service import _Candidate, _build_grid


def _candidate(answer: str, clue: str = "clue", id_: str = "1") -> _Candidate:
    return _Candidate(id=id_, answer=answer, clue=clue)


# ねこ(cat)/こい(carp)/いぬ(dog) chain-share こ and い, and are small enough
# that the greedy placer reliably interlocks all three regardless of the
# random tie-break order — a stable fixture for exact-shape assertions.
_INTERLOCKING_TRIO = [
    _candidate("ねこ", id_="1"),
    _candidate("こい", id_="2"),
    _candidate("いぬ", id_="3"),
]


def test_build_grid_returns_none_below_minimum():
    # Only 2 words and they don't share a kana — can't interlock at all.
    candidates = [_candidate("あい", id_="1"), _candidate("うえ", id_="2")]
    assert _build_grid(candidates) is None


def test_build_grid_returns_none_for_empty_input():
    assert _build_grid([]) is None


def test_build_grid_interlocks_words_sharing_letters():
    grid = _build_grid(_INTERLOCKING_TRIO)
    assert grid is not None
    assert grid["insufficient"] is False
    assert len(grid["words"]) == 3


def test_build_grid_skips_words_that_dont_intersect_anything():
    # ねこ/こい/いぬ interlock; ufo doesn't share a kana with any of them
    # and should simply be dropped rather than breaking the grid.
    candidates = [*_INTERLOCKING_TRIO, _candidate("ユーフォー", id_="4")]
    grid = _build_grid(candidates)
    assert grid is not None
    placed_ids = {w["id"] for w in grid["words"]}
    assert len(placed_ids) == 3


def test_build_grid_words_actually_share_letters_at_intersections():
    grid = _build_grid(_INTERLOCKING_TRIO)
    assert grid is not None

    words_by_id = {w["id"]: w for w in grid["words"]}
    cell_letters: dict[tuple[int, int], set[str]] = {}
    for cell in grid["cells"]:
        if cell["blocked"]:
            continue
        for word_id in cell["word_ids"]:
            word = words_by_id[word_id]
            offset_from_start = (
                (cell["col"] - word["col"]) if word["direction"] == "across"
                else (cell["row"] - word["row"])
            )
            expected_letter = word["word"][offset_from_start]
            cell_letters.setdefault((cell["row"], cell["col"]), set()).add(expected_letter)

    # If a cell is shared by 2+ words (an intersection), every word touching
    # it must agree on the letter — that's the entire point of "interlocking."
    for letters in cell_letters.values():
        assert len(letters) == 1


def test_build_grid_at_least_one_real_intersection_exists():
    grid = _build_grid(_INTERLOCKING_TRIO)
    assert grid is not None
    intersecting_cells = [cell for cell in grid["cells"] if len(cell["word_ids"]) > 1]
    assert len(intersecting_cells) >= 1


def test_build_grid_no_blocked_cell_has_word_ids():
    grid = _build_grid(_INTERLOCKING_TRIO)
    assert grid is not None
    for cell in grid["cells"]:
        if cell["blocked"]:
            assert cell["word_ids"] == []
            assert cell["letter"] is None
        else:
            assert cell["word_ids"] != []
            assert cell["letter"] is not None


def test_build_grid_filters_out_single_character_words():
    candidates = [_candidate("あ", id_="1"), _candidate("い", id_="2"), _candidate("う", id_="3")]
    assert _build_grid(candidates) is None
