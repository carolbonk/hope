from __future__ import annotations

import pytest
from hope_core.web import SearchResult
from hope_discovery.urls import canonicalize, is_blocked, order_candidates, same_site


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "http://www.Example.org/Grants/?utm_source=x&id=3#apply",
            "https://example.org/Grants?id=3",
        ),
        ("https://example.org/grants/", "https://example.org/grants"),
        ("https://example.org/", "https://example.org"),
        ("https://example.org/a?fbclid=1&gclid=2", "https://example.org/a"),
        ("mailto:grants@example.org", None),
        ("not a url", None),
    ],
)
def test_canonicalize(raw: str, expected: str | None) -> None:
    assert canonicalize(raw) == expected


def r(url: str) -> SearchResult:
    return SearchResult(url=url, title=url.rsplit("/", 1)[-1], snippet="")


def test_blocklist_known_and_round_robin() -> None:
    for blocked in (
        "https://facebook.com/x",
        "https://m.youtube.com/watch?v=1",
        "https://instrumentl.com/grants/x",
        "https://grantwatch.com/grant/1",
        "https://candid.org/find-funding/x",
    ):
        assert is_blocked(canonicalize(blocked) or ""), blocked
    assert not is_blocked("https://candid.org/about")
    assert same_site("https://a.example.org/x", "https://www.b.example.org/y")
    assert not same_site("https://example.org/x", "https://other.org/x")

    results = [
        [r("https://a.org/1"), r("https://a.org/2"), r("https://www.facebook.com/a")],
        [r("http://www.a.org/1/"), r("https://b.org/1")],
        [r("https://c.org/1"), r("https://known.org/1")],
    ]
    links, found, skipped = order_candidates(results, {"https://known.org/1"}, cap=30)
    assert [u for u, _ in links] == [
        "https://a.org/1",
        "https://c.org/1",
        "https://a.org/2",
        "https://b.org/1",
    ]
    assert skipped == 1 and found == 6
    many = [[r(f"https://site{q}.org/{i}") for i in range(10)] for q in range(5)]
    capped, _, _ = order_candidates(many, set(), cap=30)
    assert len(capped) == 30 and capped[0][0] == "https://site0.org/0"
    assert capped[1][0] == "https://site1.org/0"
