"""URL canonicalisation, blocklists and candidate ordering (H2 step 4)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from hope_core.web import SearchResult

TRACKING_PARAMS = {"gclid", "fbclid", "mc_cid", "mc_eid"}
SOCIAL_HOSTS = {
    "facebook.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
    "reddit.com",
    "pinterest.com",
}
PAYWALLED = (
    "instrumentl.com",
    "grantwatch.com",
    "grantstation.com",
    "foundationdirectory.org",
    "candid.org/find-funding",
)
_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "edu", "ac", "gob", "or", "ne"}


def canonicalize(url: str) -> str | None:
    """https, lowercase host without `www.`, no fragment, tracking params or trailing `/`."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    host = host.removeprefix("www.")
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
        ]
    )
    path = parts.path.rstrip("/")
    return urlunsplit(("https", host, path, query, ""))


def domain(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def registrable_domain(url: str) -> str:
    labels = domain(url).split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def same_site(a: str, b: str) -> bool:
    return registrable_domain(a) == registrable_domain(b) != ""


def is_blocked(canonical: str) -> bool:
    host = domain(canonical)
    if any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS):
        return True
    bare = canonical.removeprefix("https://")
    return any(
        bare == p or bare.startswith(p + "/") or ("/" not in p and host.endswith("." + p))
        for p in PAYWALLED
    )


def order_candidates(
    results: Sequence[Sequence[SearchResult]], known: Iterable[str], cap: int
) -> tuple[list[tuple[str, str]], int, int]:
    """Round-robin by rank across queries.

    Returns ([(canonical_url, title)], unique links found, links skipped as known).
    """
    known_set = set(known)
    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    skipped_known = 0
    for rank in range(max((len(r) for r in results), default=0)):
        for per_query in results:
            if rank >= len(per_query):
                continue
            hit = per_query[rank]
            url = canonicalize(hit.url)
            if url is None or url in seen:
                continue
            seen.add(url)
            if is_blocked(url):
                continue
            if url in known_set:
                skipped_known += 1
                continue
            ordered.append((url, hit.title))
    return ordered[:cap], len(seen), skipped_known
