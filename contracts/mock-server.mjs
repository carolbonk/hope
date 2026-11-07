import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
export const manifest = JSON.parse(readFileSync(join(here, "manifest.json"), "utf8"));
export const endpoints = manifest.workflows.flatMap((w) => w.endpoints.map((e) => ({ ...e, workflow: w.id })));

const toRegex = (path) => new RegExp(`^${path.replace(/\{[^}]+\}/g, "[^/]+")}$`);
const routes = endpoints.map((e) => ({ ...e, re: toRegex(e.path) }));

export function match(method, pathname) {
  return routes.find((r) => r.method === method && r.re.test(pathname)) ?? null;
}

// Scenario choice, most specific first: ?mock=<scenario>, header `x-mock-scenario: <endpoint.id>=<scenario>[, ...]`,
// env MOCK_SCENARIOS="<endpoint.id>=<scenario>,...", a query value naming a scenario (?status=saved, ?format=md),
// then the endpoint's default.
const envChoices = parseChoices(process.env.MOCK_SCENARIOS ?? "");
function parseChoices(s) {
  return Object.fromEntries(
    s.split(",").map((p) => p.trim().split("=")).filter((p) => p.length === 2 && p[0] && p[1]),
  );
}

export function scenarioFor(route, url, headers = {}) {
  const fromQuery = url.searchParams.get("mock");
  const fromHeader = parseChoices(String(headers["x-mock-scenario"] ?? ""))[route.id];
  const fromParams = [...url.searchParams.values()].find((v) => route.scenarios[v]);
  const name = fromQuery ?? fromHeader ?? envChoices[route.id] ?? fromParams ?? route.default;
  return route.scenarios[name] ? name : null;
}

export function loadMock(route, name) {
  return JSON.parse(readFileSync(join(here, route.scenarios[name]), "utf8"));
}

export function handle(req, res) {
  const url = new URL(req.url ?? "/", "http://mock.local");
  const origin = req.headers.origin;
  const cors = origin
    ? {
        "access-control-allow-origin": origin,
        "access-control-allow-credentials": "true",
        "access-control-allow-headers": "content-type, if-match, x-mock-scenario",
        "access-control-allow-methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "access-control-expose-headers": "etag",
      }
    : {};
  if (req.method === "OPTIONS") {
    res.writeHead(204, cors).end();
    return;
  }
  if (url.pathname === "/" || url.pathname === "/__mock") {
    res.writeHead(200, { "content-type": "application/json", ...cors });
    res.end(JSON.stringify(endpoints.map((e) => ({ id: e.id, method: e.method, path: e.path, default: e.default, scenarios: Object.keys(e.scenarios) })), null, 2));
    return;
  }
  const route = match(req.method ?? "GET", url.pathname);
  if (!route) {
    res.writeHead(404, { "content-type": "application/problem+json", ...cors });
    res.end(JSON.stringify({ type: "about:blank", title: "No such endpoint in contracts/manifest.json", status: 404, code: "not_in_contract" }));
    return;
  }
  const name = scenarioFor(route, url, req.headers);
  if (!name) {
    res.writeHead(400, { "content-type": "application/problem+json", ...cors });
    res.end(JSON.stringify({ type: "about:blank", title: `Unknown scenario for ${route.id}`, status: 400, code: "unknown_scenario", scenarios: Object.keys(route.scenarios) }));
    return;
  }
  const mock = loadMock(route, name);
  const headers = { ...cors, "x-mock-scenario": `${route.id}=${name}`, ...mock.headers };
  if (mock.body_text !== undefined) {
    res.writeHead(mock.status, headers).end(mock.body_text);
  } else if (mock.body === null) {
    res.writeHead(mock.status, headers).end();
  } else {
    res.writeHead(mock.status, { "content-type": "application/json", ...headers }).end(JSON.stringify(mock.body));
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.MOCK_PORT ?? 8000);
  createServer(handle).listen(port, () => {
    console.log(`Hope mock API on http://localhost:${port}/v1 (${endpoints.length} endpoints). List: http://localhost:${port}/__mock`);
  });
}
