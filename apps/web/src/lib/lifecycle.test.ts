import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { OPPORTUNITY_STATES, PROTECTED_PROFILE_PATHS, STEP_UP_MFA_GATES, TERMINAL_STATES, TRANSITIONS, nextStates } from "./lifecycle";

const SCHEMAS = resolve(import.meta.dirname, "../../../../packages/core/src/hope_core/schemas");
const read = (file: string) => readFileSync(resolve(SCHEMAS, file), "utf8");

function enumMembers(src: string, cls: string): Map<string, string> {
  const body = src.split(`class ${cls}(StrEnum):`)[1]?.split(/\n\n/)[0] ?? "";
  return new Map([...body.matchAll(/^\s+(\w+) = "([^"]+)"/gm)].map((m) => [m[1] ?? "", m[2] ?? ""]));
}

describe("lifecycle mirror matches hope_core", () => {
  const src = read("lifecycle.py");
  const states = enumMembers(src, "OpportunityState");
  const names = (list: string) => [...list.matchAll(/S\.(\w+)/g)].map((m) => states.get(m[1] ?? "")).sort();

  it("has the same states in the same order", () => {
    expect([...states.values()]).toEqual([...OPPORTUNITY_STATES]);
  });

  it("has the same transition table", () => {
    const table = src.split("TRANSITIONS")[1]?.split("\n}\n")[0] ?? "";
    const parsed = Object.fromEntries(
      [...table.matchAll(/S\.(\w+): frozenset\(\{([^}]*)\}\)/g)].map((m) => [states.get(m[1] ?? ""), names(m[2] ?? "")]),
    );
    const mirror = Object.fromEntries(Object.entries(TRANSITIONS).map(([k, v]) => [k, [...(v ?? [])].sort()]));
    expect(mirror).toEqual(parsed);
  });

  it("has the same terminal states", () => {
    const terminal = /TERMINAL[^=]*= frozenset\(\s*\{([^}]*)\}/.exec(src)?.[1] ?? "";
    expect([...TERMINAL_STATES].sort()).toEqual(names(terminal));
  });

  it("mirrors step-up MFA gates and protected profile paths", () => {
    const hitl = read("hitl.py");
    const gates = enumMembers(hitl, "Gate");
    const stepUp = /STEP_UP_MFA_GATES = frozenset\(\s*\{([^}]*)\}/.exec(hitl)?.[1] ?? "";
    expect([...STEP_UP_MFA_GATES].sort()).toEqual([...stepUp.matchAll(/Gate\.(\w+)/g)].map((m) => gates.get(m[1] ?? "")).sort());
    const paths = /PROTECTED_PROFILE_PATHS[^=]*= \(([^)]*)\)/.exec(read("agency_profile.py"))?.[1] ?? "";
    expect([...PROTECTED_PROFILE_PATHS]).toEqual([...paths.matchAll(/"(\w+)"/g)].map((m) => m[1]));
  });

  it("allows expiry only before submission", () => {
    expect(nextStates("Drafting")).toContain("Expired");
    expect(nextStates("Submitted")).not.toContain("Expired");
    expect(nextStates("Declined")).toEqual([]);
  });
});
