"""One live discovery run in memory, to see what reaches the deck and why pages fail.

`HOPE_OPENAI_API_KEY=... uv run python -m hope_discovery.live_check [--json out.json]`

Uses H1's demo profile and request, real OpenAI search and the live web. Nothing is written to
the database. Prints counts, each grant with its amount and deadline, and fetch failures by code
and site.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from typing import Any
from uuid import uuid4

from hope_core.model_gateway import MockProvider, ModelGateway, default_gateway
from hope_core.web import FetchError, Page, RealWebTools, SearchResult, WebTools

from hope_discovery import mock
from hope_discovery.agent import DiscoveryAgent
from hope_discovery.demo import DEMO_REQUEST, demo_profile
from hope_discovery.urls import domain


class RecordingWeb:
    """Passes calls through and remembers each failed fetch (`code` is `FetchError.code`)."""

    def __init__(self, web: WebTools) -> None:
        self.web = web
        self.failures: list[tuple[str, str]] = []

    def search(self, query: str, max_results: int = 8) -> list[SearchResult]:
        return self.web.search(query, max_results)

    def fetch(self, url: str) -> Page:
        try:
            return self.web.fetch(url)
        except FetchError as exc:
            self.failures.append((url, exc.code))
            raise


def run(gateway: ModelGateway, web: WebTools) -> dict[str, Any]:
    repo = mock.MemoryRepo(demo_profile(), *DEMO_REQUEST)
    recording = RecordingWeb(web)
    started = time.monotonic()
    result = DiscoveryAgent(repo, gateway, recording).run(uuid4())
    grants = [
        {
            "title": c.title,
            "url": c.url,
            "amount_max_minor": c.amount_max.amount_minor if c.amount_max else None,
            "amount_text": c.amount_text,
            "deadline": c.deadline.isoformat() if c.deadline else None,
            "deadline_text": c.deadline_text,
        }
        for c in repo.candidates.values()
    ]
    return {
        "elapsed_s": round(time.monotonic() - started),
        "counts": result["counts"],
        "grants": grants,
        "complete": sum(1 for g in grants if g["amount_max_minor"] and g["deadline"]),
        "failures": [{"url": u, "code": c} for u, c in recording.failures],
    }


def report(out: dict[str, Any]) -> str:
    grants = out["grants"]
    lines = [
        f"{len(grants)} grants found in {out['elapsed_s']} s: {out['complete']} complete cards, "
        f"{len(grants) - out['complete']} check cards",
        "counts: " + ", ".join(f"{k}={v}" for k, v in out["counts"].items()),
    ]
    for g in grants:
        amount = f"${g['amount_max_minor'] // 100:,}" if g["amount_max_minor"] else "no amount"
        lines.append(
            f"- {g['title'][:70]} | {amount} | {g['deadline'] or g['deadline_text'] or '-'}"
        )
    failures = out["failures"]
    if failures:
        lines.append(f"{len(failures)} fetch failures by code:")
        codes = Counter(f["code"] for f in failures)
        lines += [f"  {code}: {n}" for code, n in codes.most_common()]
        sites = Counter(f"{domain(f['url'])} ({f['code']})" for f in failures)
        lines.append("by site: " + ", ".join(f"{s} x{n}" for s, n in sites.most_common()))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", help="also write the full result to this file")
    args = parser.parse_args(argv)
    gateway = default_gateway()
    if any(isinstance(p, MockProvider) for p in gateway.providers):
        print("Set HOPE_OPENAI_API_KEY for a live run.", file=sys.stderr)
        return 2
    out = run(gateway, RealWebTools())
    print(report(out))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(out, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
