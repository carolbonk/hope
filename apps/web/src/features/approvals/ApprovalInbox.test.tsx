import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithApi } from "@/test/render";
import { ApprovalInbox } from "./ApprovalInbox";

const card = async (summary: RegExp) => (await screen.findByText(summary)).closest("section") as HTMLElement;

describe("ApprovalInbox", () => {
  it("shows only requests for the user's roles, each with an SLA", async () => {
    renderWithApi(<ApprovalInbox />);
    expect(await screen.findByText(/^Budget sign-off:/)).toBeInTheDocument();
    expect(screen.queryByText(/^Board approval:/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/^SLA /).length).toBeGreaterThanOrEqual(5);
  });

  it("asks for step-up MFA on HITL-2 and shows the 409 stale-hash error", async () => {
    const user = userEvent.setup();
    const { api } = renderWithApi(<ApprovalInbox />);
    const spy = vi.spyOn(api, "submitSignal");
    const budget = await card(/^Budget sign-off:/);
    await user.click(within(budget).getByRole("button", { name: /^Approve/ }));

    const dialog = await screen.findByRole("dialog", { name: "Step-up verification required" });
    const verify = within(dialog).getByRole("button", { name: /Verify and approve/ });
    expect(verify).toBeDisabled();
    await user.type(within(dialog).getByLabelText(/6-digit/), "123456");
    await user.click(verify);

    expect(await within(budget).findByRole("alert")).toHaveTextContent(/Stale artifact \(409\)/);
    const [, , body, opts] = spy.mock.calls[0] ?? [];
    expect(body?.artifact_hash).toMatch(/^sha256:/);
    expect(opts?.stepUpToken).toBe("mfa-placeholder:123456");
  });

  it("requires a comment to request changes and records decisions without MFA for HITL-4", async () => {
    const user = userEvent.setup();
    renderWithApi(<ApprovalInbox />);
    const exec = await card(/^Executive approval:/);
    await user.click(within(exec).getByRole("button", { name: "Request changes" }));
    expect(within(exec).getByRole("alert")).toHaveTextContent("Add a comment");
    await user.type(within(exec).getByLabelText("Comment"), "Tighten the evaluation plan.");
    await user.click(within(exec).getByRole("button", { name: "Request changes" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(await screen.findByText(/Request changes recorded for HITL-4/)).toBeInTheDocument();
  });
});
