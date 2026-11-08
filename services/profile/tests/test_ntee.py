"""H1 NTEE data file and search."""

from __future__ import annotations

from hope_profile import ntee


def test_data_file_complete() -> None:
    codes = ntee.all_codes()
    assert len(codes) >= 400
    assert len({c.code for c in codes}) == len(codes)
    for code in ("E32", "F30", "O50", "K31", "L41", "E", "P20"):
        assert ntee.is_code(code), code
    assert ntee.label("E32") == "Community Clinics"
    assert ntee.label("F30") == "Mental Health Treatment"
    assert all(c.label and c.group_label and c.code.startswith(c.group) for c in codes)


def test_groups_for_empty_query() -> None:
    groups = ntee.search("", limit=50)
    assert len(groups) == 26
    assert [g.code for g in groups] == sorted("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    assert ntee.search("   ", limit=5) == groups


def test_search_ranking() -> None:
    assert ntee.search("E32")[0].code == "E32"
    assert ntee.search("e32")[0].code == "E32"
    clinic = [c.code for c in ntee.search("clinic", limit=5)]
    assert clinic[0] == "E32"
    assert "K31" in [c.code for c in ntee.search("food bank", limit=5)]
    assert len(ntee.search("health", limit=3)) == 3
    assert ntee.search("zzzzqqq") == []
    first = ntee.search("clinic")[0].model_dump()
    assert set(first) == {"code", "label", "group", "group_label"}
