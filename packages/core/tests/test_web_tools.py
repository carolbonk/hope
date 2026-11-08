from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from hope_core.web import FetchError, RecordedWebTools, fetch, page_key

FIXTURES = Path(__file__).parent / "fixtures" / "web"
PUBLIC = "93.184.216.34"
HOSTS = {
    "grants.example.org": [PUBLIC],
    "internal.example.org": ["10.0.0.5"],
    "mixed.example.org": [PUBLIC, "127.0.0.1"],
    "metadata.example.org": ["169.254.169.254"],
}


def resolver(host: str) -> list[str]:
    return HOSTS[host]


def site(routes: dict[str, httpx.Response]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == PUBLIC, "connection must go to the checked address"
        key = f"{request.headers['host']}{request.url.path}"
        return routes.get(key, httpx.Response(404))

    return httpx.MockTransport(handler)


def test_fetch_extracts_html_text_and_links() -> None:
    html = (FIXTURES / "raw" / "grant.html").read_text()
    transport = site({"grants.example.org/rhaf": httpx.Response(200, html=html)})
    page = fetch("https://grants.example.org/rhaf", resolver=resolver, transport=transport)
    assert page.title == "Rural Health Access Fund | Cascade Community Foundation"
    assert "Awards range up to $50,000" in page.text
    assert "tracking" not in page.text
    urls = [link.url for link in page.links]
    assert "https://grants.example.org/files/rhaf-guidelines.pdf" in urls
    assert "https://cascadecf.example.org/grants/rhaf/faq" in urls
    assert not any(u.startswith("mailto:") for u in urls)
    assert page.content_type == "text/html"


def test_fetch_extracts_pdf_text() -> None:
    pdf = (FIXTURES / "raw" / "guidelines.pdf").read_bytes()
    transport = site(
        {
            "grants.example.org/g.pdf": httpx.Response(
                200, content=pdf, headers={"content-type": "application/pdf"}
            )
        }
    )
    page = fetch("https://grants.example.org/g.pdf", resolver=resolver, transport=transport)
    assert page.content_type == "application/pdf"
    assert "Applications are due March 31, 2027" in page.text
    assert page.title == "Rural Health Access Fund Guidelines"


def test_fetch_follows_checked_redirects() -> None:
    transport = site(
        {
            "grants.example.org/old": httpx.Response(301, headers={"location": "/new"}),
            "grants.example.org/new": httpx.Response(200, html="<title>New</title><p>Hello</p>"),
        }
    )
    page = fetch("http://grants.example.org/old", resolver=resolver, transport=transport)
    assert page.final_url == "http://grants.example.org/new"
    assert page.url == "http://grants.example.org/old"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost.internal/",
        "http://[::1]/",
        "http://10.0.0.1/",
        "http://192.168.1.10/",
        "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.example.org/",
        "http://internal.example.org/",
        "http://mixed.example.org/",
        "http://224.0.0.1/",
        "http://0.0.0.0/",
        "http://240.0.0.1/",
        "ftp://grants.example.org/file",
        "file:///etc/passwd",
        "http://grants.example.org:8080/",
        "https://grants.example.org:22/",
        "redirect:http://127.0.0.1/admin",
        "redirect:http://169.254.169.254/",
        "redirect:http://internal.example.org/",
        "redirect:gopher://grants.example.org/",
    ],
)
def test_fetch_blocks_internal_addresses(url: str) -> None:
    def resolve(host: str) -> list[str]:
        return HOSTS.get(host, ["127.0.0.1"])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": url.removeprefix("redirect:")})
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        raise AssertionError(f"unchecked request to {request.url}")

    target = "http://grants.example.org/start" if url.startswith("redirect:") else url
    with pytest.raises(FetchError) as err:
        fetch(target, resolver=resolve, transport=httpx.MockTransport(handler))
    assert err.value.code == "blocked_address"


def test_fetch_respects_robots_txt() -> None:
    transport = site(
        {
            "grants.example.org/robots.txt": httpx.Response(
                200, text="User-agent: *\nDisallow: /private\n"
            ),
            "grants.example.org/private/x": httpx.Response(200, html="<p>secret</p>"),
        }
    )
    with pytest.raises(FetchError) as err:
        fetch("https://grants.example.org/private/x", resolver=resolver, transport=transport)
    assert err.value.code == "robots_disallowed"


def test_fetch_rejects_too_many_redirects() -> None:
    transport = site(
        {"grants.example.org/loop": httpx.Response(302, headers={"location": "/loop"})}
    )
    with pytest.raises(FetchError) as err:
        fetch("https://grants.example.org/loop", resolver=resolver, transport=transport)
    assert err.value.code == "too_many_redirects"


def test_recorded_lookup_rules() -> None:
    tools = RecordedWebTools(FIXTURES)
    results = tools.search("  Community   HEALTH grants Wenatchee washington ")
    assert len(results) == 3
    assert (
        tools.search("Community health grants wenatchee washington", max_results=1) == results[:1]
    )
    assert tools.search("an unknown query") == []
    page = tools.fetch(results[0].url)
    assert page.url == results[0].url and page.content_type
    with pytest.raises(FetchError):
        tools.fetch("https://unknown.example.org/")


def test_recorded_fixtures_are_complete() -> None:
    tools = RecordedWebTools(FIXTURES)
    searches = sorted((FIXTURES / "search").glob("*.json"))
    pages = sorted((FIXTURES / "pages").glob("*.json"))
    assert len(searches) == 3 and len(pages) >= 6
    for path in pages:
        page = tools.fetch(json.loads(path.read_text())["url"])
        assert page_key(page.url) == path.stem and page.content_type
    pdfs = [p for p in pages if '"application/pdf"' in p.read_text()]
    assert len(pdfs) == 1
