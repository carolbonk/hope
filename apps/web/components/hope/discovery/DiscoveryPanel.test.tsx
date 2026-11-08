import { act, fireEvent, render, screen } from "@testing-library/react";
import { ProblemError } from "@/lib/api/http";
import { I18nProvider } from "@/components/I18nProvider";
import { DiscoveryProblem } from "./api";
import { DiscoveryPanel } from "./DiscoveryPanel";
import { FixtureDiscoveryApi, W3 } from "./fixture";
import type { DiscoveryApi, DiscoveryJobView } from "./types";

const JOB = W3.running().job.job_id;
const flush = () => act(async () => {});
const advance = (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)));

function show(api: DiscoveryApi, reload = vi.fn()) {
  const utils = render(<DiscoveryPanel api={api} online reload={reload} />);
  return { ...utils, reload };
}

async function startWith(keywords: string, location = "Chelan County, WA") {
  fireEvent.change(screen.getByLabelText("Focus keywords"), { target: { value: keywords } });
  fireEvent.change(screen.getByLabelText("Location"), { target: { value: location } });
  fireEvent.click(screen.getByRole("button", { name: "Find new grants" }));
  await flush();
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: false });
  vi.setSystemTime(new Date("2026-11-08T15:00:00Z"));
  window.localStorage.clear();
});
afterEach(() => {
  vi.useRealTimers();
  Object.defineProperty(document, "hidden", { configurable: true, value: false });
});

it("offline shows the line and makes no request", async () => {
  const api = new FixtureDiscoveryApi();
  render(<DiscoveryPanel api={api} online={false} />);
  await flush();
  expect(screen.getByText("Live search needs Hope's server. These are demo cards.")).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  expect(api.calls.list).toEqual([]);
});

it("start body and running", async () => {
  const api = new FixtureDiscoveryApi();
  show(api);
  await flush();
  expect(api.calls.list).toEqual([1]);
  expect(screen.getByText("Last search: 57 minutes ago · 3 grants (2 new)")).toBeInTheDocument();
  await startWith("one, two, three, four, five, six");
  expect(screen.getByText("Up to 5 keywords.")).toBeInTheDocument();
  expect(api.calls.start).toEqual([]);
  await startWith(" dental , Dental, rural, x ", "   ");
  expect(api.calls.start).toEqual([{ focus_keywords: ["dental", "rural"], location: null }]);
  expect(screen.getByRole("heading", { name: "Finding grants" })).toBeInTheDocument();
  expect(screen.getByText("◌ Starting")).toBeInTheDocument();
});

it("start errors copy", async () => {
  const cases: [DiscoveryApi["startJob"], RegExp][] = [
    [() => Promise.reject(new DiscoveryProblem(422, "profile_incomplete", "x", [], { missing: ["programs"] })), /Hope needs your mission and at least one program first\./],
    [() => Promise.reject(new DiscoveryProblem(429, "daily_limit", "x", [], { limit: 20, resets_at: "2026-11-09T05:00:00Z" })), /You've run 20 searches today\. You can search again in 14 hours\./],
    [() => Promise.reject(new ProblemError(422, "validation_error", "x", [{ field: "location", code: "x", message: "Bad location" }])), /Bad location/],
    [() => Promise.reject(new ProblemError(0, "network_error", "offline")), /We couldn't start the search\. Try again\./],
    [() => Promise.reject(new ProblemError(503, "http_503", "down")), /We couldn't start the search\. Try again\./],
  ];
  for (const [startJob, copy] of cases) {
    const fx = new FixtureDiscoveryApi();
    const { unmount } = show({ listJobs: (n) => fx.listJobs(n), getJob: (i, s) => fx.getJob(i, s), startJob });
    await flush();
    await startWith("dental");
    expect(screen.getByText(copy)).toBeInTheDocument();
    if (copy.source.startsWith("Hope needs")) expect(screen.getByRole("link", { name: "Complete profile" })).toHaveAttribute("href", "/hope/profile");
    unmount();
  }
  const fx = new FixtureDiscoveryApi({ runningJob: true });
  const api: DiscoveryApi = { listJobs: async () => W3.listOk(), getJob: (i, s) => fx.getJob(i, s), startJob: (b) => fx.startJob(b) };
  show(api);
  await flush();
  await startWith("dental");
  expect(screen.getByText("A search is already running. Showing it now.")).toBeInTheDocument();
  expect(fx.calls.get[0]).toEqual([JOB, 0]);
  expect(screen.getByRole("heading", { name: "Finding grants" })).toBeInTheDocument();
});

it("polling since_seq progress counters and backoff", async () => {
  const api = new FixtureDiscoveryApi();
  show(api);
  await flush();
  await startWith("dental");
  await advance(1499);
  expect(api.calls.get).toEqual([]);
  await advance(1);
  expect(api.calls.get).toEqual([[JOB, 0]]);
  expect(screen.getByText("Searches 6/6 · Pages 7/21 · Grants 1")).toBeInTheDocument();
  expect(screen.getByText("Scoring fit: Rural Oral Health Access Grant 2027", { selector: "p[title]" })).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "53");
  expect(screen.getByText("What Hope searched for (6)")).toBeInTheDocument();
  const seq = W3.running().last_seq;
  await advance(1500);
  expect(api.calls.get).toEqual([[JOB, 0], [JOB, seq]]);
  expect(screen.getByRole("heading", { name: "✓ Search complete" })).toBeInTheDocument();
  await advance(10_000);
  expect(api.calls.get).toHaveLength(2);

  fireEvent.click(screen.getByRole("button", { name: "Search again" }));
  Object.defineProperty(document, "hidden", { configurable: true, value: true });
  await startWith("dental");
  await advance(1500);
  expect(api.calls.get).toHaveLength(2);
  await advance(3500);
  expect(api.calls.get).toHaveLength(3);
});

it("done variants needs check and reload", async () => {
  const api = new FixtureDiscoveryApi();
  const { reload } = show(api);
  await flush();
  await startWith("dental");
  await advance(3000);
  expect(screen.getByText("Found 3 grants · 2 new · 1 skipped because the deadline passed · took 2 min 41 s")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show the new grants" }));
  expect(reload).toHaveBeenCalledOnce();
  for (const [key, copy] of [
    ["none", "Hope didn't find open grants this time. Try a focus keyword or a broader location."],
    ["stop", "Stopped early to keep the search quick. Read 7 of 21 pages."],
    ["check", "1 found grant needs a check (no amount or deadline on the page):"],
  ]) {
    fireEvent.click(screen.getByRole("button", { name: "Search again" }));
    await startWith(key!);
    await advance(3000);
    expect(screen.getByText(copy!)).toBeInTheDocument();
  }
  expect(screen.getByRole("link", { name: /Mobile Health Equipment Fund/ })).toHaveAttribute("href", "https://ncwmedicalfund.example.org/mobile-equipment");
  expect(screen.queryByText(/Fictional/)).not.toBeInTheDocument();
});

it("failed and lost connection", async () => {
  const api = new FixtureDiscoveryApi();
  show(api);
  await flush();
  await startWith("fail");
  await advance(1500);
  expect(screen.getByRole("heading", { name: "The search didn't finish" })).toBeInTheDocument();
  expect(screen.getByText(/Web search is unavailable right now\. Try again in a few minutes\./, { selector: "p.text-navy" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await flush();
  expect(api.calls.start).toHaveLength(2);

  let fail = true;
  const flaky: DiscoveryApi = {
    listJobs: async () => ({ ...W3.listOk(), running_job_id: JOB }),
    startJob: (b) => api.startJob(b),
    getJob: async () => {
      if (fail) throw new ProblemError(0, "network_error", "offline");
      return W3.done();
    },
  };
  render(<DiscoveryPanel api={flaky} online />);
  await flush();
  await advance(3000);
  expect(screen.getByText("Lost connection to the search. It's still running on the server.")).toBeInTheDocument();
  fail = false;
  fireEvent.click(screen.getByRole("button", { name: "Reconnect" }));
  await flush();
  expect(screen.getAllByRole("heading", { name: "✓ Search complete" }).length).toBeGreaterThan(0);
});

it("resumes running job on mount", async () => {
  const api = new FixtureDiscoveryApi({ runningJob: true });
  show(api);
  await flush();
  expect(api.calls.get).toEqual([[JOB, 0]]);
  expect(screen.getByText("● Running 0:44")).toBeInTheDocument();
});

it("throttled announcements and progressbar aria", async () => {
  let n = 0;
  const frame = (): DiscoveryJobView => {
    const v = W3.running();
    n += 1;
    v.job.progress.current_step = `Step ${n}`;
    v.steps = [];
    return v;
  };
  const api: DiscoveryApi = {
    listJobs: async () => W3.listEmpty(),
    startJob: async () => new Promise(() => {}),
    getJob: async () => frame(),
  };
  const { container, unmount } = show(api);
  await flush();
  expect(screen.getByText("Your first search usually takes 1-3 minutes.")).toBeInTheDocument();
  await startWith("dental");
  expect(screen.getByRole("button", { name: "Starting…" })).toBeDisabled();
  expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
  unmount();

  const resumed = { ...api, listJobs: async () => ({ ...W3.listOk(), running_job_id: JOB }) };
  const view = render(<DiscoveryPanel api={resumed} online />);
  await flush();
  const live = () => view.container.querySelector('[aria-live="polite"]')!.textContent;
  expect(live()).toBe("Step 1");
  await advance(1500);
  await advance(1500);
  expect(screen.getByText("Step 3")).toBeInTheDocument();
  expect(live()).toBe("Step 1");
  await advance(1500);
  await advance(1500);
  expect(live()).toBe("Step 5");
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "53 percent, 1 grant found");
  void container;
});

it("renders es copy", async () => {
  render(
    <I18nProvider locale="es">
      <DiscoveryPanel api={new FixtureDiscoveryApi()} online />
      <DiscoveryPanel online={false} />
    </I18nProvider>,
  );
  await flush();
  expect(screen.getByRole("button", { name: "Buscar nuevas subvenciones" })).toBeInTheDocument();
  expect(screen.getAllByRole("heading", { name: "Buscar subvenciones reales" })).toHaveLength(2);
  expect(screen.getByText("La búsqueda en vivo necesita el servidor de Hope. Estas son tarjetas de demostración.")).toBeInTheDocument();
});
