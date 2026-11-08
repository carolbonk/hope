"""DiscoveryAgent: profile → plan → search → read → extract → parse → fit → save (H2 section B)."""

from __future__ import annotations

import logging
import threading
import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from hope_core.model_gateway import (
    BudgetExceededError,
    Message,
    ModelGateway,
    ModelTier,
    RunBudget,
    untrusted,
)
from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.hackathon import DiscoveryProgress, GrantCandidate, JobStatus
from hope_core.settings import get_settings
from hope_core.web import FetchError, Link, Page, SearchResult, WebTools

from hope_discovery import prompts
from hope_discovery.digest import ProfileDigest, build_digest
from hope_discovery.extract import VerifiedExtraction, VerifiedQuote, clean_text, verify_extraction
from hope_discovery.fit import FitResult, WebSource, postprocess_fit
from hope_discovery.models import FitAssessment, PageExtraction, QueryPlan
from hope_discovery.parse import parse_amount, parse_deadline
from hope_discovery.planner import postprocess_plan
from hope_discovery.repo import DiscoveryRepo
from hope_discovery.settings import DiscoverySettings, get_discovery_settings
from hope_discovery.urls import canonicalize, domain, order_candidates

log = logging.getLogger(__name__)

SEARCH_UNAVAILABLE = "Web search is unavailable right now. Try again in a few minutes."
SOMETHING_WRONG = "Something went wrong while searching. Your earlier results are safe."
YEARLESS_CONCERN = "Deadline year not stated. Check the funder page."
PROGRAM_TOTAL_CONCERN = "The amount on the page looks like total program funding, not one award."
COUNT_KEYS = (
    "urls_found",
    "pages_read",
    "candidates_new",
    "candidates_updated",
    "skipped_expired",
    "skipped_not_grant",
    "skipped_poor_fit",
    "skipped_known",
    "failed_pages",
    "queries_failed",
)
SKIP_REASONS = {
    "funder_overview": "a funder overview, not an open call",
    "list_or_directory": "a list of grants, not one grant",
    "news_or_blog": "news, not a grant",
    "not_relevant": "not a grant",
    "open_opportunity": "not clearly an open grant",
}


class DiscoveryFailed(RuntimeError):
    """Ends the job `failed` with a message that is safe to show."""


def empty_counts() -> dict[str, int]:
    return dict.fromkeys(COUNT_KEYS, 0)


def grant_id_for(url: str, tenant_id: UUID | None = None) -> UUID:
    """Stable per tenant: `grant_id` is a global key, but URLs are only unique per tenant."""
    return uuid5(NAMESPACE_URL, f"{tenant_id or get_settings().tenant_id}:{url}")


def format_elapsed(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s" if m else f"{s}s"


@dataclass
class _Event:
    kind: str
    text: str
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Outcome:
    """What reading one link produced. Built in a worker thread; written in URL order."""

    url: str
    events: list[_Event] = field(default_factory=list)
    pages_read: int = 0
    failed: bool = False
    skipped_expired: bool = False
    skipped_not_grant: bool = False
    skipped_poor_fit: bool = False
    candidate: GrantCandidate | None = None
    fit_score: int | None = None
    stop: bool = False  # budget ran out inside this page


class _Stop(Exception):
    pass


class DiscoveryAgent:
    def __init__(
        self,
        repo: DiscoveryRepo,
        gateway: ModelGateway,
        web: WebTools,
        settings: DiscoverySettings | None = None,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        budget: RunBudget | None = None,
    ) -> None:
        self.repo = repo
        self.gateway = gateway
        self.web = web
        self.s = settings or get_discovery_settings()
        self.clock = clock
        self.now = now
        self.budget = budget or RunBudget(
            max_calls=self.s.max_llm_calls, max_tokens=self.s.max_tokens
        )
        self._detail_lock = threading.Lock()
        self._details_used = 0

    # --- bookkeeping --------------------------------------------------------------------------

    def _step(
        self, text: str, kind: str = "info", status: JobStatus = "running", **fields: Any
    ) -> None:
        self.progress.current_step = text[:300]
        self.repo.progress(self.job_id, self.progress, status)
        self.repo.event(self.job_id, kind, text, **fields)

    def _write(self, ev: _Event) -> None:
        self._step(ev.text, ev.kind, **ev.fields)

    def _elapsed(self) -> float:
        return self.clock() - self.started

    # --- the run ------------------------------------------------------------------------------

    def run(self, job_id: UUID) -> dict[str, Any]:
        self.job_id = job_id
        self.started = self.clock()
        self.progress = DiscoveryProgress(current_step="Starting")
        self.counts = empty_counts()
        try:
            return self._run()
        except (DiscoveryFailed, LookupError):
            raise
        except Exception as exc:
            # Frames only: exception messages can carry model or page text.
            log.error(
                "discovery %s failed: %s\n%s",
                job_id,
                type(exc).__name__,
                "".join(traceback.format_tb(exc.__traceback__)),
            )
            self._safe_error(SOMETHING_WRONG)
            raise DiscoveryFailed(SOMETHING_WRONG) from None

    def _safe_error(self, text: str) -> None:
        try:
            self.repo.set_counts(self.job_id, self.counts)
            self._step(text, "error")
        except Exception:
            log.error("discovery %s: could not record the failure", self.job_id)

    def _run(self) -> dict[str, Any]:
        today = self.now().date()
        self._step("Reading your profile")
        profile = self.repo.load_profile()
        if profile is None:
            raise DiscoveryFailed("Finish your profile first")
        keywords, location = self.repo.load_request(self.job_id)
        digest = build_digest(profile, location)
        self.annual_budget_minor = profile.financials.annual_operating_budget.amount_minor

        queries = self._plan(digest, keywords, location, today)
        self.repo.set_queries(self.job_id, queries)
        self.progress.queries_total = len(queries)

        results = self._search(queries)
        since = self.now() - timedelta(days=self.s.known_url_days)
        all_urls = [c for rs in results for r in rs if (c := canonicalize(r.url))]
        known = self.repo.known_urls(all_urls, since) if all_urls else set()
        links, found, skipped_known = order_candidates(results, known, self.s.max_candidate_urls)
        self.counts["urls_found"] = found
        self.counts["skipped_known"] = skipped_known
        self._step(f"Found {len(links)} unique links from {len(queries)} searches")

        stopped = self._read_all(links, profile, digest, today)
        self.repo.set_counts(self.job_id, self.counts)
        if stopped is not None:
            self._step(
                f"Stopped early after {format_elapsed(self._elapsed())}:"
                f" read {stopped} of {len(links)} links.",
                "warning",
            )
        found_total = self.counts["candidates_new"] + self.counts["candidates_updated"]
        self._step(f"Done: {found_total} grants found, {self.counts['candidates_new']} new")
        return {"counts": self.counts, "queries": queries}

    # --- 1. plan ------------------------------------------------------------------------------

    def _plan(
        self, digest: ProfileDigest, keywords: list[str], location: str | None, today: date
    ) -> list[str]:
        self._step("Planning searches")
        messages = [
            Message("system", prompts.PLAN_SYSTEM),
            Message(
                "user", prompts.plan_user(today.isoformat(), digest.render(), keywords, location)
            ),
        ]
        plan: QueryPlan | None
        try:
            plan = self.gateway.structured(ModelTier.MID, messages, QueryPlan, self.budget)
        except LookupError:
            raise
        except Exception:
            plan = None
            self._step("Couldn't plan searches, using standard ones", "warning")
        return postprocess_plan(plan, digest, keywords, location, today, self.s)

    # --- 2. search ----------------------------------------------------------------------------

    def _search(self, queries: list[str]) -> list[list[SearchResult]]:
        results: list[list[SearchResult]] = []
        for q in queries:
            if self._elapsed() >= self.s.job_timeout_s:
                break
            self.progress.current_step = f"Searching: {q}"[:300]
            self.repo.progress(self.job_id, self.progress, "running")
            try:
                hits = self.web.search(q, self.s.results_per_query)
            except Exception as exc:
                log.warning("search failed (%s)", type(exc).__name__)
                self.counts["queries_failed"] += 1
                self.progress.queries_done += 1
                self._step(f"Search failed: {q}", "warning", query=q)
                results.append([])
                continue
            self.progress.queries_done += 1
            self._step(f"Searching: {q}", "query", query=q, result_count=len(hits))
            results.append(hits)
        if results and self.counts["queries_failed"] == len(results):
            self._safe_error(SEARCH_UNAVAILABLE)
            raise DiscoveryFailed(SEARCH_UNAVAILABLE)
        return results

    # --- 3. read, extract, fit, save ----------------------------------------------------------

    def _read_all(
        self,
        links: list[tuple[str, str]],
        profile: AgencyProfile,
        digest: ProfileDigest,
        today: date,
    ) -> int | None:
        """Returns None when every link was read, else how many were (stopped early)."""
        n = max(1, self.s.fetch_concurrency)
        done = 0
        with ThreadPoolExecutor(max_workers=n, thread_name_prefix="hope-discovery") as pool:
            for start in range(0, len(links), n):
                if self._elapsed() >= self.s.job_timeout_s:
                    return done
                batch = links[start : start + n]
                outcomes = list(pool.map(lambda lt: self._read_one(lt, digest, today), batch))
                stop = False
                for outcome in outcomes:
                    self._record(outcome)
                    done += 1
                    stop = stop or outcome.stop
                if stop:
                    return done
        return None

    def _record(self, o: _Outcome) -> None:
        for ev in o.events:
            if ev.kind == "page":
                self.progress.pages_read += 1
                self.counts["pages_read"] += 1
            if ev.kind == "candidate" and o.candidate is not None:
                is_new = not self.repo.url_exists(o.candidate.url)
                saved = self.repo.upsert(o.candidate)
                self.counts["candidates_new" if is_new else "candidates_updated"] += 1
                self.progress.candidates_found += 1
                ev.fields.update(grant_id=saved.grant_id, is_new=is_new, url=saved.url)
            self._write(ev)
        self.counts["failed_pages"] += int(o.failed)
        self.counts["skipped_expired"] += int(o.skipped_expired)
        self.counts["skipped_not_grant"] += int(o.skipped_not_grant)
        self.counts["skipped_poor_fit"] += int(o.skipped_poor_fit)

    def _read_one(self, link: tuple[str, str], digest: ProfileDigest, today: date) -> _Outcome:
        url, hint = link
        o = _Outcome(url)
        try:
            self._read_into(o, url, hint, digest, today)
        except BudgetExceededError:
            o.stop = True
            o.candidate = None
            o.events = [e for e in o.events if e.kind != "candidate"]
        return o

    def _fetch(self, url: str) -> Page | None:
        try:
            page = self.web.fetch(url)
        except FetchError as exc:
            log.info("fetch failed url=%s code=%s", url, exc.code)
            return None
        log.info("fetched url=%s chars=%d", url, len(page.text))
        return page

    def _read_into(
        self, o: _Outcome, url: str, hint: str, digest: ProfileDigest, today: date
    ) -> None:
        site = domain(url)
        o.events.append(_Event("page", f"Reading: {hint or site}", {"url": url}))
        page = self._fetch(url)
        if page is None:
            o.events.pop()
            o.events.append(_Event("skip", f"Couldn't read {site}", {"url": url}))
            o.failed = True
            return
        final_url = canonicalize(page.final_url or url) or url
        texts = [clean_text(page.text)[: self.s.page_chars_to_llm]]
        links = page.links[:40]
        ext = self._extract(final_url, page.title, texts, links, today)
        if ext is None:
            o.events.append(_Event("skip", f"Couldn't read {site}", {"url": url}))
            o.failed = True
            return
        v = verify_extraction(ext, texts, final_url, page.title, links, self.s)
        if v.keep and v.detail_url and self._take_detail():
            detail = self._fetch(v.detail_url)
            if detail is not None:
                o.events.append(
                    _Event(
                        "page", f"Checking details on {domain(v.detail_url)}", {"url": v.detail_url}
                    )
                )
                texts2 = [*texts, clean_text(detail.text)[: self.s.page_chars_to_llm]]
                ext2 = self._extract(final_url, page.title, texts2, links, today)
                if ext2 is not None:
                    v2 = verify_extraction(ext2, texts2, final_url, page.title, links, self.s)
                    if v2.keep:
                        v2.detail_url = v.detail_url
                        v = v2
        if not v.keep:
            if v.kind == "closed_or_past":
                o.skipped_expired = True
                o.events.append(
                    _Event("skip", f"Skipping {v.title}: deadline has passed", {"url": url})
                )
            else:
                o.skipped_not_grant = True
                reason = SKIP_REASONS.get(v.kind, "not a grant")
                o.events.append(_Event("skip", f"Skipping {v.title}: {reason}", {"url": url}))
            return

        amount = parse_amount(v.amount.text) if v.amount else None
        deadline = parse_deadline(v.deadline.text, today) if v.deadline else None
        concerns = list(v.concerns)
        if amount and amount.max and self._is_program_total(amount.max.amount_minor):
            amount = None
            concerns.append(PROGRAM_TOTAL_CONCERN)
        if deadline is not None and deadline.all_dates and deadline.date is None:
            o.skipped_expired = True
            o.events.append(
                _Event("skip", f"Skipping {v.title}: deadline has passed", {"url": url})
            )
            return
        if deadline is not None and deadline.yearless:
            concerns.append(YEARLESS_CONCERN)
        rolling = (v.rolling or bool(deadline and deadline.rolling)) and (
            deadline is None or deadline.date is None
        )

        o.events.append(_Event("info", f"Scoring fit: {v.title}"))
        sources = self._web_sources(v, final_url, page.title)
        result = self._fit(digest, v, sources, concerns)
        if result is None:
            o.events.append(_Event("warning", f"Couldn't score {v.title}", {"url": final_url}))
            return
        if result.blocked or result.score < self.s.min_fit_score:
            o.skipped_poor_fit = True
            why = "not eligible" if result.blocked else f"weak fit ({result.score})"
            o.events.append(_Event("skip", f"Skipping {v.title}: {why}", {"url": final_url}))
            return
        o.candidate = GrantCandidate(
            grant_id=grant_id_for(final_url),
            title=v.title,
            funder=v.funder,
            url=final_url,
            summary=v.summary,
            amount_text=v.amount.text[:500] if v.amount else None,
            amount_max=amount.max if amount else None,
            deadline_text="Rolling" if rolling else (v.deadline.text[:500] if v.deadline else None),
            deadline=None if rolling else (deadline.date if deadline else None),
            eligibility_summary=v.eligibility_summary,
            fit_score=result.score,
            fit_reasons=result.reasons,
            concerns=result.concerns,
            citations=result.citations,
            status="new",
            found_by_job_id=self.job_id,
            discovered_at=self.now(),
        )
        o.fit_score = result.score
        o.events.append(
            _Event("candidate", f"Saved: {v.title} (fit {result.score})", {"url": final_url})
        )

    def _is_program_total(self, amount_minor: int) -> bool:
        budget = getattr(self, "annual_budget_minor", 0)
        return budget > 0 and amount_minor > budget * self.s.max_award_budget_ratio

    def _take_detail(self) -> bool:
        with self._detail_lock:
            if self._details_used >= self.s.max_detail_fetches:
                return False
            self._details_used += 1
            return True

    def _extract(
        self, url: str, title: str, texts: list[str], links: list[Link], today: date
    ) -> PageExtraction | None:
        pages = [
            untrusted(t, label="web_page").replace(
                '<untrusted kind="web_page">', f'<untrusted kind="web_page" n="{i}">', 1
            )
            for i, t in enumerate(texts, start=1)
        ]
        link_lines = [f"[{i}] {lk.text[:80]} -> {lk.url}" for i, lk in enumerate(links, start=1)]
        messages = [
            Message("system", prompts.EXTRACT_SYSTEM),
            Message("user", prompts.extract_user(today.isoformat(), url, title, pages, link_lines)),
        ]
        for _ in range(2):  # one retry
            try:
                ext: PageExtraction = self.gateway.structured(
                    ModelTier.MID, messages, PageExtraction, self.budget
                )
                return ext
            except (LookupError, BudgetExceededError):
                raise
            except Exception as exc:
                log.warning("extract failed url=%s (%s)", url, type(exc).__name__)
        return None

    def _web_sources(self, v: VerifiedExtraction, url: str, title: str) -> list[WebSource]:
        quotes: list[VerifiedQuote] = [q for q in (v.amount, v.deadline) if q] + v.eligibility
        sources: list[WebSource] = []
        for q in quotes:
            src_url = v.detail_url if q.page == 2 and v.detail_url else url
            sources.append(WebSource(f"W{len(sources) + 1}", src_url, title or v.title, q.text))
        return sources

    def _fit(
        self,
        digest: ProfileDigest,
        v: VerifiedExtraction,
        sources: list[WebSource],
        concerns: list[str],
    ) -> FitResult | None:
        quote_lines = [f'[{w.ref}] "{w.quote}" ({w.url})' for w in sources]
        messages = [
            Message("system", prompts.FIT_SYSTEM),
            Message(
                "user", prompts.fit_user(digest.render(), v.title, v.funder, v.summary, quote_lines)
            ),
        ]
        for _ in range(2):  # one retry
            try:
                fit = self.gateway.structured(ModelTier.MID, messages, FitAssessment, self.budget)
            except (LookupError, BudgetExceededError):
                raise
            except Exception as exc:
                log.warning("fit failed (%s)", type(exc).__name__)
                continue
            return postprocess_fit(
                fit, sources, digest, self.now(), concerns, always_cite=[w.ref for w in sources]
            )
        return None
