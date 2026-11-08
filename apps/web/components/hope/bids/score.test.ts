import { ALL_REQS } from "@/lib/hope/dossier";
import { demoOpportunities } from "@/lib/hope/demo";
import { DEMO_PROFILE, emptyProfile } from "@/lib/hope/store";
import { scoreRow } from "./score";

const TODAY = new Date("2026-11-07T12:00:00");
const opp = demoOpportunities(TODAY)[0]!;
const allOnFile = { ...DEMO_PROFILE, dossier: Object.fromEntries(ALL_REQS.map((id) => [id, { status: "declared" as const }])) };
const isoIn = (days: number) => new Date(TODAY.getTime() + days * 86_400_000).toISOString().slice(0, 10);

/** Every row reachable by varying focus overlap, amount and deadline, so a threshold can be hit exactly. */
const rows = DEMO_PROFILE.focusAreas.flatMap((_, n) =>
  Array.from({ length: n + 2 }, (_, k) => [...DEMO_PROFILE.focusAreas.slice(0, k), ...Array.from({ length: n + 1 - k }, (_, i) => `other_${i}`)]).flatMap((focusAreas) =>
    [0.3, 0.8, 2].flatMap((share) =>
      Array.from({ length: 61 }, (_, d) =>
        scoreRow({ ...opp, focusAreas, amountMax: DEMO_PROFILE.annualBudget! * share, deadline: isoIn(d) }, allOnFile, TODAY, "meets"),
      ),
    ),
  ),
);
const at = (score: number) => {
  const row = rows.find((r) => r.score === score);
  expect(row, `no input combination scores ${score}`).toBeDefined();
  return row!;
};

describe("scoreRow", () => {
  it("is the documented weighted sum, rounded to one decimal", () => {
    const r = scoreRow(opp, DEMO_PROFILE, TODAY, "meets");
    const { focus, geo, size, effort, time } = r.dims;
    expect(r.score).toBe(Math.round((0.35 * focus + 0.2 * geo + 0.2 * size + 0.15 * (100 - effort) + 0.1 * time) * 10) / 10);
  });

  it("counts unknown amount, budget and date as 50, never as a guess", () => {
    const r = scoreRow({ ...opp, amountMax: null, deadline: null }, emptyProfile(), TODAY, "needs_review");
    expect(r.dims.size).toBe(50);
    expect(r.dims.time).toBe(50);
    expect(r.days).toBeNull();
  });

  it("skips anything not qualified or already closed", () => {
    expect(scoreRow(opp, DEMO_PROFILE, TODAY, "not_qualified").rec).toBe("skip");
    expect(scoreRow({ ...opp, deadline: "2026-11-01" }, DEMO_PROFILE, TODAY, "meets").rec).toBe("skip");
  });

  it.each([
    [70, "pursue"],
    [69.9, "consider"],
    [55, "consider"],
    [54.9, "watch"],
  ] as const)("recommends at the boundary: %s → %s", (score, rec) => {
    expect(at(score).rec).toBe(rec);
  });

  it("counts only an unknown budget as 50 when the amount is known", () => {
    const r = scoreRow({ ...opp, amountMax: 10_000 }, { ...DEMO_PROFILE, annualBudget: null }, TODAY, "meets");
    expect(r.dims.size).toBe(50);
    expect(r.dims.time).not.toBe(50);
  });

  it("scores effort as 10 per pending requirement, capped at 100", () => {
    expect(scoreRow(opp, allOnFile, TODAY, "meets").dims.effort).toBe(0);
    const rest = Object.fromEntries(Object.entries(allOnFile.dossier).filter(([id]) => !["ein_letter", "bylaws", "board_list"].includes(id)));
    expect(scoreRow(opp, { ...allOnFile, dossier: rest }, TODAY, "meets").dims.effort).toBe(30);
    expect(scoreRow(opp, { ...allOnFile, dossier: {} }, TODAY, "meets").dims.effort).toBe(100);
  });
});
