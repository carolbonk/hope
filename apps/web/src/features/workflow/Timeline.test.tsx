import { render, screen } from "@testing-library/react";
import { FixtureApi } from "@/api/fixture";
import { FIXED_NOW } from "@/test/render";
import { Timeline, timelineSteps } from "./Timeline";

describe("Timeline", () => {
  it("shows visited states, the current state and the remaining happy path", async () => {
    const api = new FixtureApi({ now: () => FIXED_NOW });
    const wf = (await api.listWorkflows()).find((w) => w.state === "AwaitingBudgetSignoff")!;
    const view = await api.getWorkflow(wf.workflow_id);
    const steps = timelineSteps(view);
    expect(steps.filter((s) => s.status === "current").map((s) => s.state)).toEqual(["AwaitingBudgetSignoff"]);
    expect(steps.at(-1)).toMatchObject({ state: "PostAward", status: "upcoming" });
    render(<Timeline workflow={view} />);
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent(/Awaiting Budget Signoff/i);
  });
});
