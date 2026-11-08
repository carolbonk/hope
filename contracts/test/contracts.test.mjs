import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { endpoints, manifest, match, loadMock } from "../mock-server.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const specs = join(here, "..", "..", "docs", "specs", "screens");
const HACKATHON_SCREENS = ["SC00", "SC01", "SC09", "SC11", "SC24", "SC25", "SC26", "SC27", "SC28"];

test("every endpoint has a unique id, a default scenario and loadable mocks", () => {
  const ids = new Set();
  for (const e of endpoints) {
    assert.ok(!ids.has(e.id), `duplicate id ${e.id}`);
    ids.add(e.id);
    assert.ok(e.scenarios[e.default], `${e.id}: default scenario ${e.default} missing`);
    for (const name of Object.keys(e.scenarios)) {
      const m = loadMock(e, name);
      assert.equal(typeof m.status, "number", `${e.id}/${name}: status`);
      if (m.status >= 400) {
        assert.equal(m.headers["content-type"], "application/problem+json", `${e.id}/${name}: problem content type`);
        assert.equal(m.body.status, m.status, `${e.id}/${name}: body.status`);
        assert.match(m.body.code, /^[a-z_]+$/, `${e.id}/${name}: code`);
      }
    }
  }
});

test("method + path pairs are unique and every route resolves to itself", () => {
  for (const e of endpoints) {
    const concrete = e.path.replace(/\{[^}]+\}/g, "x1");
    assert.equal(match(e.method, concrete)?.id, e.id, `${e.method} ${e.path}`);
  }
});

test("money is integer minor units, never floats", () => {
  const walk = (v, where) => {
    if (Array.isArray(v)) v.forEach((x, i) => walk(x, `${where}[${i}]`));
    else if (v && typeof v === "object") {
      if ("amount_minor" in v) assert.ok(Number.isInteger(v.amount_minor), `${where}: amount_minor must be an integer`);
      for (const [k, x] of Object.entries(v)) walk(x, `${where}.${k}`);
    }
  };
  for (const e of endpoints) for (const name of Object.keys(e.scenarios)) walk(loadMock(e, name), `${e.id}/${name}`);
});

test("every endpoint a hackathon screen spec calls is in the contract", () => {
  const files = readdirSync(specs).filter((f) => HACKATHON_SCREENS.some((s) => f.startsWith(s)));
  assert.equal(files.length, HACKATHON_SCREENS.length);
  const missing = [];
  for (const f of files) {
    const text = readFileSync(join(specs, f), "utf8");
    for (const m of text.matchAll(/\b(GET|POST|PUT|PATCH|DELETE) `?(\/v1\/[A-Za-z0-9_{}\/.-]*)/g)) {
      const path = m[2].replace(/[.]$/, "").replace(/\{[^}]+\}/g, "x1");
      if (!match(m[1], path)) missing.push(`${f}: ${m[1]} ${m[2]}`);
    }
  }
  assert.deepEqual(missing, []);
});

test("every workflow lists its screens, spec, ticket and classified steps", () => {
  for (const w of manifest.workflows) {
    assert.match(w.spec, /^H[0-7]$/);
    assert.ok(Number.isInteger(w.issue) || (w.issue === null && w.spec === "H7"), `${w.id}: issue`);
    assert.ok(w.screens.length > 0);
    for (const s of w.steps) assert.ok(["code", "llm", "web"].includes(s.kind), `${w.id}: ${s.name}`);
  }
});
