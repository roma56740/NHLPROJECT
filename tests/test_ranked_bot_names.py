"""Фиксированные ники Ranked-ботов: ровно 100, без изменений, без зависимости от
OVR/состава пользователя, без повторов в одной выборке, fallback на встроенную
копию при повреждённом файле. См. app/services/ranked_bot_names.py.
"""

import inspect

from app.services import ranked_bot_names


def test_exactly_100_nicknames_loaded():
    ranked_bot_names.reset_cache_for_tests()
    names = ranked_bot_names.get_all_nicknames()
    assert len(names) == 100


def test_all_nicknames_unique():
    ranked_bot_names.reset_cache_for_tests()
    names = ranked_bot_names.get_all_nicknames()
    assert len(names) == len(set(names))


def test_spelling_matches_embedded_reference_exactly():
    ranked_bot_names.reset_cache_for_tests()
    names = ranked_bot_names.get_all_nicknames()
    assert names == list(ranked_bot_names.EMBEDDED_NICKNAMES)


def test_no_forbidden_technical_names():
    ranked_bot_names.reset_cache_for_tests()
    names = ranked_bot_names.get_all_nicknames()
    lowered = {n.lower() for n in names}
    for forbidden in ("player123", "bot123", "user123"):
        assert forbidden not in lowered


def test_old_random_generator_not_used_for_ranked_bots():
    import app.services.ranked_core as ranked_core

    source = inspect.getsource(ranked_core.find_ranked_opponent)
    assert "random.choice(BOT_NAMES)" not in source
    assert "ranked_bot_names.pick_nickname" in source


def test_pick_nickname_only_from_fixed_list():
    ranked_bot_names.reset_cache_for_tests()
    names = set(ranked_bot_names.get_all_nicknames())
    for _ in range(50):
        assert ranked_bot_names.pick_nickname() in names


def test_pick_nickname_signature_has_no_user_dependent_params():
    import inspect as _inspect

    params = list(_inspect.signature(ranked_bot_names.pick_nickname).parameters)
    assert params == ["exclude"]


def test_no_repeats_within_one_selection_while_unique_available():
    ranked_bot_names.reset_cache_for_tests()
    used: set[str] = set()
    picked = []
    for _ in range(100):
        name = ranked_bot_names.pick_nickname(exclude=used)
        assert name not in used
        used.add(name)
        picked.append(name)
    assert len(set(picked)) == 100

    # 101-й пик при исчерпанном списке допускает повтор (не падает, не блокируется).
    name_101 = ranked_bot_names.pick_nickname(exclude=used)
    assert name_101 in ranked_bot_names.get_all_nicknames()


def test_corrupted_file_falls_back_to_embedded_copy(monkeypatch, tmp_path):
    missing_path = tmp_path / "does_not_exist.txt"
    monkeypatch.setattr(ranked_bot_names, "NICKNAMES_PATH", missing_path)
    ranked_bot_names.reset_cache_for_tests()
    try:
        names = ranked_bot_names.get_all_nicknames()
        assert names == list(ranked_bot_names.EMBEDDED_NICKNAMES)
    finally:
        ranked_bot_names.reset_cache_for_tests()


def test_diagnostics_reports_expected_fields():
    ranked_bot_names.reset_cache_for_tests()
    diag = ranked_bot_names.diagnostics()
    assert diag["loaded_count"] == 100
    assert diag["expected_count"] == 100
    assert diag["count_matches_expected"] is True
    assert diag["has_duplicates"] is False
    assert len(diag["sample"]) == 5
