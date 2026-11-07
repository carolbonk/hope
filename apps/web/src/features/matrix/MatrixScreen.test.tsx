import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithApi } from "@/test/render";
import { MatrixScreen } from "./MatrixScreen";

const bodyRows = () => within(screen.getByRole("table")).getAllByRole("row").slice(1);

describe("MatrixScreen", () => {
  it("renders ranked rows, filters them and opens the detail drawer", async () => {
    const user = userEvent.setup();
    renderWithApi(<MatrixScreen />);
    await screen.findByRole("table", { name: "Ranked grant opportunities" });
    const all = bodyRows().length;
    expect(all).toBe(8);

    const recommendation = screen.getByRole("group", { name: "Recommendation" });
    await user.click(within(recommendation).getByRole("button", { name: "Pursue" }));
    expect(bodyRows().length).toBeLessThan(all);
    expect(within(recommendation).getByRole("button", { name: "Pursue" })).toHaveAttribute("aria-pressed", "true");

    await user.click(within(screen.getByRole("group", { name: "Recommendation" })).getByRole("button", { name: /^All/ }));
    await user.click(within(screen.getByRole("group", { name: "Eligibility" })).getByRole("button", { name: "Ineligible" }));
    expect(bodyRows()).toHaveLength(1);

    await user.click(within(bodyRows()[0]!).getByRole("button", { name: /Details for/ }));
    const drawer = await screen.findByRole("dialog");
    for (const heading of ["Why this ranking", "Matched programs", "Risks"]) expect(within(drawer).getByText(heading)).toBeInTheDocument();
  });
});
