import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { DeadlineCalendar } from "./DeadlineCalendar";
import { DeadlineTable } from "./DeadlineTable";
import { DeadlineViewTabs, type DeadlineView } from "./DeadlineViewTabs";
import type { DeadlineItem } from "./items";

const today = new Date(2026, 10, 7);
const items: DeadlineItem[] = [
  { id: "a1", oppId: "opp-soon", name: "Back-to-School Sponsorship", funder: "Tidal Bank", stage: "eligibility", deadline: "2026-11-16", days: 9 },
  { id: "a2", oppId: "opp-later", name: "Public Murals Fund", funder: "Lumen Arts", stage: "saved", deadline: "2026-12-05", days: 28 },
];

function Harness() {
  const [view, setView] = useState<DeadlineView>("table");
  return (
    <>
      <DeadlineViewTabs value={view} onChange={setView} label="Deadline view" labels={{ table: "Table", calendar: "Calendar" }} />
      {view === "table" ? <DeadlineTable items={items} /> : <DeadlineCalendar items={items} today={today} />}
    </>
  );
}

describe("deadline views", () => {
  it("switches between table and calendar by click and arrow keys", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const table = screen.getByRole("tab", { name: "Table" });
    const calendar = screen.getByRole("tab", { name: "Calendar" });
    expect(table).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("link", { name: /Public Murals Fund/ })).toHaveAttribute("href", "/hope/applications/opp-later");

    await user.click(calendar);
    expect(calendar).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "November 2026" })).toBeInTheDocument();

    await user.keyboard("{ArrowLeft}");
    expect(table).toHaveAttribute("aria-selected", "true");
    expect(table).toHaveFocus();
  });

  it("calendar chips link to each application and months can be paged", async () => {
    const user = userEvent.setup();
    render(<DeadlineCalendar items={items} today={today} />);
    const chip = screen.getByTitle("Back-to-School Sponsorship");
    expect(chip).toHaveAttribute("href", "/hope/applications/opp-soon");
    expect(screen.queryByTitle("Public Murals Fund")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next month" }));
    const heading = screen.getByRole("heading", { name: "December 2026" });
    expect(heading).toBeInTheDocument();
    expect(within(document.body).getByTitle("Public Murals Fund")).toHaveAttribute("href", "/hope/applications/opp-later");
  });
});
