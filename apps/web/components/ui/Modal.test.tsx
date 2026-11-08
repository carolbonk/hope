import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Modal } from "./Modal";

function Paste() {
  const [open, setOpen] = useState(true);
  const [text, setText] = useState("");
  return (
    <div data-testid="glass" style={{ backdropFilter: "blur(8px)" }}>
      <Modal open={open} title="Paste the form" onClose={() => setOpen(false)}>
        <label htmlFor="t">Form</label>
        <textarea id="t" value={text} onChange={(e) => setText(e.target.value)} />
      </Modal>
    </div>
  );
}

describe("Modal", () => {
  it("renders on <body>, outside any glass ancestor", () => {
    render(<Paste />);
    const dialog = screen.getByRole("dialog", { name: "Paste the form" });
    expect(screen.getByTestId("glass").contains(dialog)).toBe(false);
    expect(dialog.closest("body")).toBe(document.body);
  });

  it("keeps focus in the field while typing with an inline onClose", async () => {
    render(<Paste />);
    const field = screen.getByLabelText("Form");
    await userEvent.click(field);
    await userEvent.type(field, "Question 1 (500 words)");
    expect(field).toHaveValue("Question 1 (500 words)");
    expect(field).toHaveFocus();
  });

  it("closes on Escape with the latest onClose", async () => {
    render(<Paste />);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
