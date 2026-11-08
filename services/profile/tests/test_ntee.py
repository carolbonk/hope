from __future__ import annotations

import json
import string

from hope_profile import ntee


def test_search_ranking() -> None:
    assert ntee.search("E32")[0].code == "E32"
    prefix = [c.code for c in ntee.search("e3")]
    assert prefix[0] == "E30" and prefix == sorted(prefix[: len(prefix)])
    clinic = ntee.search("clinic")
    assert clinic[0].code == "E32" and clinic[0].label == "Community Clinics"
    assert list(clinic[0].model_dump()) == ["code", "label", "group", "group_label"]
    ranks = [c.code for c in ntee.search("health", limit=50)]
    assert ranks[:1] != [] and len(ranks) <= 50
    assert ntee.search("zzzz-no-match") == []
    assert len(ntee.search("a", limit=3)) == 3


def test_groups_for_empty_query() -> None:
    groups = ntee.search("  ")
    assert [g.code for g in groups] == list(string.ascii_uppercase)
    assert groups[4].label == "Health Care"


def test_data_file_complete() -> None:
    entries = json.loads(ntee.DATA.read_text(encoding="utf-8"))
    assert len(entries) >= 400
    codes = {e["code"] for e in entries}
    assert {"E32", "F30", "O50", "K31", "L41"} <= codes
    assert len(codes) == len(entries)
    for e in entries:
        assert set(e) == {"code", "label", "group", "group_label", "keywords"}
        assert e["code"].startswith(e["group"]) and e["label"] and "<" not in e["label"]
    assert ntee.label("E32") == "Community Clinics" and ntee.label("ZZ9") is None
