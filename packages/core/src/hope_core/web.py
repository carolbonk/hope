"""Web tools (H0 section 6): an SSRF-guarded `fetch` and the M2 `search` call.

Everything here is code: whether a page is a grant is decided later, from fetched text.
Nothing is persisted.
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import socket
import time
import zipfile
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx
from pydantic import BaseModel

from hope_core.settings import HopeSettings, get_settings

USER_AGENT = "HopeBot/0.1 (+https://hope.org/bot)"
MAX_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT = 15.0
ALLOWED_PORTS = {"http": 80, "https": 443}
RETRY_AFTER_MAX = 5.0  # one retry on 429 when the site asks for at most this many seconds
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

Resolver = Callable[[str], list[str]]


class FetchError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class Link(BaseModel):
    url: str
    text: str = ""


class Page(BaseModel):
    url: str
    final_url: str
    title: str = ""
    text: str = ""
    links: list[Link] = []
    content_type: str = "text/html"


class SearchResult(BaseModel):
    url: str
    title: str
    snippet: str = ""


class WebTools(Protocol):
    def search(self, query: str, max_results: int = 8) -> list[SearchResult]: ...

    def fetch(self, url: str) -> Page: ...


# --- fetch -----------------------------------------------------------------------------------


def system_resolver(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError("dns_failed", host) from exc
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def check_url(url: str, resolver: Resolver = system_resolver) -> str:
    """Validate scheme, port and every resolved address; return the address to connect to."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_PORTS or not parts.hostname:
        raise FetchError("blocked_address", "scheme")
    try:
        port = parts.port
    except ValueError as exc:
        raise FetchError("blocked_address", "port") from exc
    if port is not None and port not in ALLOWED_PORTS.values():
        raise FetchError("blocked_address", "port")
    host = parts.hostname
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        addresses = resolver(host)
    if not addresses:
        raise FetchError("dns_failed", host)
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global or ip.is_multicast or ip.is_reserved:
            raise FetchError("blocked_address", host)
    return addresses[0]


def _pinned_request(client: httpx.Client, url: str, address: str) -> httpx.Response:
    """GET `url`, connecting to the already-checked `address` (no second DNS lookup)."""
    parts = urlsplit(url)
    ip = ipaddress.ip_address(address)
    netloc = f"[{ip}]" if ip.version == 6 else str(ip)
    if parts.port:
        netloc += f":{parts.port}"
    target = parts._replace(netloc=netloc).geturl()
    host_header = parts.hostname or ""
    if parts.port:
        host_header += f":{parts.port}"
    request = client.build_request(
        "GET",
        target,
        headers={"Host": host_header, "User-Agent": USER_AGENT},
        extensions={"sni_hostname": parts.hostname} if parts.scheme == "https" else {},
    )
    response = client.send(request, stream=True)
    try:
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise FetchError("too_large", url)
    finally:
        response.close()
    response._content = bytes(body)
    return response


def _get(client: httpx.Client, url: str, resolver: Resolver) -> tuple[str, httpx.Response]:
    current = url
    for _hop in range(MAX_REDIRECTS + 1):
        address = check_url(current, resolver)
        response = _pinned_request(client, current, address)
        location = response.headers.get("location")
        if response.is_redirect and location:
            current = urljoin(current, location)
            continue
        return current, response
    raise FetchError("too_many_redirects", url)


class _HtmlScan(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.links: list[Link] = []
        self.text: list[str] = []
        self._href: str | None = None
        self._anchor: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            href = dict(attrs).get("href")
            self._href = href
            self._anchor = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._href is not None:
            absolute, _ = urldefrag(urljoin(self.base_url, self._href.strip()))
            if urlsplit(absolute).scheme in ALLOWED_PORTS:
                self.links.append(Link(url=absolute, text=" ".join("".join(self._anchor).split())))
            self._href = None

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_title:
            self.title += data
            return
        self.text.append(data)
        if self._href is not None:
            self._anchor.append(data)


def _dedupe(links: list[Link]) -> list[Link]:
    seen: dict[str, Link] = {}
    for link in links:
        seen.setdefault(link.url, link)
    return list(seen.values())


def parse_html(html: str, url: str, final_url: str) -> Page:
    import trafilatura

    scan = _HtmlScan(final_url)
    scan.feed(html)
    text = trafilatura.extract(html, include_links=False, include_tables=True) or ""
    if not text.strip():
        text = "\n".join(line.strip() for line in "".join(scan.text).splitlines() if line.strip())
    return Page(
        url=url,
        final_url=final_url,
        title=" ".join(scan.title.split()),
        text=text,
        links=_dedupe(scan.links),
        content_type="text/html",
    )


def parse_pdf(data: bytes, url: str, final_url: str) -> Page:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    text = "\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
    title = str(reader.metadata.title or "") if reader.metadata else ""
    return Page(
        url=url, final_url=final_url, title=title, text=text, content_type="application/pdf"
    )


def parse_docx(data: bytes, url: str, final_url: str) -> Page:
    """Paragraph text of a Word file (`word/document.xml`); no DTDs, capped unzipped size."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as docx:
            if docx.getinfo("word/document.xml").file_size > MAX_BYTES * 4:
                raise FetchError("too_large", url)
            xml = docx.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise FetchError("unsupported_content_type", DOCX) from exc
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise FetchError("unsupported_content_type", DOCX)
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise FetchError("unsupported_content_type", DOCX) from exc
    lines = ("".join(t.text or "" for t in p.iter(f"{_W}t")).strip() for p in root.iter(f"{_W}p"))
    text = "\n".join(line for line in lines if line)
    return Page(url=url, final_url=final_url, text=text, content_type=DOCX)


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds a 429 asks us to wait, if short enough to wait once; else None (give up)."""
    value = response.headers.get("retry-after", "1").strip()
    if not value.isdigit() or float(value) > RETRY_AFTER_MAX:
        return None
    return float(value)


def _robots_allows(client: httpx.Client, url: str, resolver: Resolver) -> bool:
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        _, response = _get(client, robots_url, resolver)
    except FetchError as exc:
        if exc.code == "blocked_address":
            raise
        return True
    except httpx.HTTPError as exc:
        raise FetchError("network", f"robots.txt: {type(exc).__name__}") from exc
    if response.status_code >= 400:
        return True
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser.can_fetch(USER_AGENT, url)


def fetch(
    url: str,
    *,
    resolver: Resolver = system_resolver,
    transport: httpx.BaseTransport | None = None,
    respect_robots: bool = True,
    sleep: Callable[[float], None] = time.sleep,
) -> Page:
    url, _ = urldefrag(url.strip())
    check_url(url, resolver)
    with httpx.Client(transport=transport, timeout=TIMEOUT, follow_redirects=False) as client:
        if respect_robots and not _robots_allows(client, url, resolver):
            raise FetchError("robots_disallowed", url)
        try:
            final_url, response = _get(client, url, resolver)
            if response.status_code == 429 and (wait := _retry_after(response)) is not None:
                sleep(wait)
                final_url, response = _get(client, url, resolver)
        except httpx.HTTPError as exc:
            raise FetchError("network", type(exc).__name__) from exc
    if response.status_code >= 400:
        raise FetchError(f"http_{response.status_code}", url)
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type == "application/pdf" or response.content[:5] == b"%PDF-":
        return parse_pdf(response.content, url, final_url)
    if content_type == DOCX or (
        response.content[:2] == b"PK" and urlsplit(final_url).path.lower().endswith(".docx")
    ):
        return parse_docx(response.content, url, final_url)
    if content_type in ("text/html", "application/xhtml+xml", ""):
        return parse_html(response.text, url, final_url)
    if content_type.startswith("text/"):
        return Page(url=url, final_url=final_url, text=response.text, content_type=content_type)
    raise FetchError("unsupported_content_type", content_type)


# --- search (M2) -----------------------------------------------------------------------------


def _check_query(query: str, max_results: int) -> str:
    query = query.strip()
    if not 1 <= len(query) <= 200:
        raise ValueError("query must be 1-200 characters")
    if not 1 <= max_results <= 10:
        raise ValueError("max_results must be 1-10")
    return query


def parse_search_response(raw: dict[str, Any], max_results: int = 8) -> list[SearchResult]:
    """Keep only the `url_citation` annotations of the output message; discard the prose."""
    results: dict[str, SearchResult] = {}
    for item in raw.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict) or content.get("type") != "output_text":
                continue
            text = str(content.get("text") or "")
            for note in content.get("annotations") or []:
                if not isinstance(note, dict) or note.get("type") != "url_citation":
                    continue
                url, _ = urldefrag(str(note.get("url") or "").strip())
                parts = urlsplit(url)
                if parts.scheme not in ALLOWED_PORTS or not parts.hostname or url in results:
                    continue
                start, end = note.get("start_index"), note.get("end_index")
                snippet = text[start:end] if isinstance(start, int) and isinstance(end, int) else ""
                title = str(note.get("title") or "").strip() or parts.hostname
                results[url] = SearchResult(
                    url=url, title=title, snippet=" ".join(snippet.split())[:300]
                )
                if len(results) >= max_results:
                    return list(results.values())
    return list(results.values())


class RealWebTools:
    def __init__(
        self,
        settings: HopeSettings | None = None,
        *,
        openai_transport: httpx.BaseTransport | None = None,
        web_transport: httpx.BaseTransport | None = None,
        resolver: Resolver = system_resolver,
    ) -> None:
        from hope_core.openai_provider import OpenAIClient

        self.settings = settings or get_settings()
        if not self.settings.openai_api_key:
            raise ValueError("RealWebTools needs HOPE_OPENAI_API_KEY")
        self._openai = OpenAIClient(self.settings.openai_api_key, transport=openai_transport)
        self._web_transport = web_transport
        self._resolver = resolver

    def search(self, query: str, max_results: int = 8) -> list[SearchResult]:
        query = _check_query(query, max_results)
        raw = self._openai.post(
            "/responses",
            {
                "model": self.settings.openai_search_model,
                "tools": [{"type": "web_search"}],
                "input": f"Find web pages for: {query}",
            },
        )
        return parse_search_response(raw, max_results)

    def fetch(self, url: str) -> Page:
        return fetch(url, resolver=self._resolver, transport=self._web_transport)


def normalise_query(query: str) -> str:
    return " ".join(query.lower().split())


def page_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


class RecordedWebTools:
    """Replays `search/<normalised query>.json` and `pages/<sha256(url)[:16]>.json`."""

    def __init__(self, fixture_dir: Path | str) -> None:
        self.fixture_dir = Path(fixture_dir)

    def search(self, query: str, max_results: int = 8) -> list[SearchResult]:
        query = _check_query(query, max_results)
        path = self.fixture_dir / "search" / f"{normalise_query(query)}.json"
        if not path.is_file():
            return []
        data = json.loads(path.read_text())
        results = data["results"] if isinstance(data, dict) else data
        return [SearchResult.model_validate(r) for r in results][:max_results]

    def fetch(self, url: str) -> Page:
        path = self.fixture_dir / "pages" / f"{page_key(url.strip())}.json"
        if not path.is_file():
            raise FetchError("not_recorded", url)
        return Page.model_validate_json(path.read_text())


DEFAULT_FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "web"
