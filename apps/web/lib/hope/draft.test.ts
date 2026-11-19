import { demoOpportunities } from "./demo";
import { hopeTemplate, type HopeDraftRequest } from "./draft";
import { DEMO_PROFILE, emptyProfile, SECTION_IDS } from "./store";

const opp = demoOpportunities(new Date("2026-11-07T12:00:00")).find(
  (o) => o.id === "opp-bayfront-youth",
)!;
const req = (over: Partial<HopeDraftRequest> = {}): HopeDraftRequest => ({
  locale: "en",
  mode: "template",
  profile: DEMO_PROFILE,
  opportunity: opp,
  ask: 50000,
  ...over,
});
const amounts = (budget: string) =>
  budget
    .split("\n")
    .map((l) => Number(l.replace(/^.*USD /, "").replace(/,/g, "")));

it("fills all six sections from the template", () => {
  const r = hopeTemplate(req());
  expect(r.source).toBe("template");
  expect(Object.keys(r.sections).sort()).toEqual([...SECTION_IDS].sort());
  for (const s of SECTION_IDS) expect(r.sections[s].trim()).not.toBe("");
  expect(r.sections.program).toContain(opp.name);
});

it.each([50000, 1003, 2501, 999_999, 7])(
  "budget lines sum exactly to an ask of %i",
  (ask) => {
    const lines = amounts(hopeTemplate(req({ ask })).sections.budget);
    const total = lines.pop();
    expect(total).toBe(ask);
    expect(lines.reduce((t, n) => t + n, 0)).toBe(ask);
  },
);

it("marks missing profile facts and an unknown ask TO CONFIRM", () => {
  const r = hopeTemplate(req({ profile: emptyProfile(), ask: null }));
  expect(r.sections.program).toContain("[TO CONFIRM]");
  expect(r.sections.budget).not.toMatch(/\d/);
  expect(JSON.stringify(r)).not.toMatch(/NaN|null/);
});

it("drafts in Spanish for locale es", () => {
  const r = hopeTemplate(req({ locale: "es", profile: emptyProfile() }));
  expect(r.sections.program).toContain("Población");
  expect(r.sections.program).toContain("[POR CONFIRMAR]");
  expect(r.sections.program).not.toContain("[TO CONFIRM]");
  expect(r.reviewerNotes[0]).toContain("POR CONFIRMAR");
});
