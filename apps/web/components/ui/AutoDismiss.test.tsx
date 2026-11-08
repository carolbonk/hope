import { act, render, screen } from "@testing-library/react";
import { AutoDismiss, NOTICE_MS } from "./AutoDismiss";
import { TextField } from "./Field";

describe("AutoDismiss", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("removes the message after 5 seconds and reports it", () => {
    const onDismiss = vi.fn();
    render(
      <AutoDismiss onDismiss={onDismiss}>
        <p role="alert">Saved</p>
      </AutoDismiss>,
    );
    expect(NOTICE_MS).toBe(5000);
    act(() => vi.advanceTimersByTime(4900));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(100));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("hides field validation errors after 5 seconds and shows a new one again", () => {
    const { rerender } = render(<TextField label="Name" error="Enter a name." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a name.");
    act(() => vi.advanceTimersByTime(NOTICE_MS));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    rerender(<TextField label="Name" error="Name is too long." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Name is too long.");
  });
});
