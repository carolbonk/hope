import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithApi } from "@/test/render";
import { ProfileEditor } from "./ProfileEditor";

const section = (name: string) => screen.getByRole("heading", { name }).closest("section") as HTMLElement;

describe("ProfileEditor", () => {
  it("marks protected sections and submits them as HITL-0 proposals", async () => {
    const user = userEvent.setup();
    const { api } = renderWithApi(<ProfileEditor />);
    await screen.findByRole("heading", { name: "Legal identity" });
    for (const name of ["Legal identity", "Financials", "Approval hierarchy"])
      expect(within(section(name)).getByText("Requires approval (HITL-0)")).toBeInTheDocument();
    expect(within(section("Mission")).queryByText(/HITL-0/)).not.toBeInTheDocument();

    const legal = section("Legal identity");
    const name = within(legal).getByLabelText("Legal name");
    await user.clear(name);
    await user.type(name, "Riverbend Health Alliance");
    await user.click(within(legal).getByRole("button", { name: "Submit for approval" }));
    expect(await within(legal).findByText(/waiting for HITL-0 approval/)).toBeInTheDocument();
    expect((await api.getProfile()).profile.legal.legal_name).not.toBe("Riverbend Health Alliance");
    expect((await api.listHitlRequests(["finance_director", "executive_director"])).some((r) => r.gate === "HITL-0")).toBe(true);
  });

  it("validates EIN format before submitting", async () => {
    const user = userEvent.setup();
    renderWithApi(<ProfileEditor />);
    await screen.findByRole("heading", { name: "Legal identity" });
    const legal = section("Legal identity");
    const ein = within(legal).getByLabelText("EIN");
    await user.clear(ein);
    await user.type(ein, "123");
    expect(within(legal).getByText("Use the format 12-3456789.")).toBeInTheDocument();
  });
});
