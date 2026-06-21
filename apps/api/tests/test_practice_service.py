from app.services.practice_service import level_counts, parse_exclude, resolve_levels


def test_resolve_levels_exact():
    assert resolve_levels("N3", "exact") == ["N3"]


def test_resolve_levels_and_below():
    assert resolve_levels("N3", "and_below") == ["N5", "N4", "N3"]


def test_resolve_levels_and_below_floor():
    assert resolve_levels("N5", "and_below") == ["N5"]


def test_resolve_levels_and_below_hardest():
    assert resolve_levels("N1", "and_below") == ["N5", "N4", "N3", "N2", "N1"]


def test_level_counts_balanced_sums_to_total():
    counts = level_counts(["N5", "N4", "N3"], "balanced", 20)
    assert sum(counts.values()) == 20


def test_level_counts_balanced_is_even():
    counts = level_counts(["N5", "N4", "N3"], "balanced", 20)
    assert max(counts.values()) - min(counts.values()) <= 1


def test_level_counts_challenge_sums_to_total():
    counts = level_counts(["N5", "N4", "N3"], "challenge", 20)
    assert sum(counts.values()) == 20


def test_level_counts_challenge_skews_toward_hardest():
    counts = level_counts(["N5", "N4", "N3"], "challenge", 20)
    # N3 is hardest in this range — challenge should overrepresent it
    # relative to balanced's near-even split.
    assert counts["N3"] > counts["N5"]
    assert counts["N3"] > 20 / 3


def test_level_counts_single_level_unaffected_by_distribution():
    balanced = level_counts(["N5"], "balanced", 20)
    challenge = level_counts(["N5"], "challenge", 20)
    assert balanced == challenge == {"N5": 20}


def test_level_counts_empty_levels():
    assert level_counts([], "balanced", 20) == {}


def test_parse_exclude_splits_and_trims():
    assert parse_exclude("日, 食 ,新") == {"日", "食", "新"}


def test_parse_exclude_none():
    assert parse_exclude(None) == set()


def test_parse_exclude_empty_string():
    assert parse_exclude("") == set()


def test_parse_exclude_drops_empty_segments():
    assert parse_exclude("日,,食,") == {"日", "食"}
