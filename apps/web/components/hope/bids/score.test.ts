import { demoOpportunities } from "@/lib/hope/demo";
import { DEMO_PROFILE, emptyProfile } from "@/lib/hope/store";
import { scoreRow } from "./score";

const TODAY = new Date("2026-11-07T12:00:00");
const opp = demoOpportunities(TODAY)[0]!;

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
});
