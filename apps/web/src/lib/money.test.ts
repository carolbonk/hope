import { formatBps, formatMoney, minorToMajorString, parseMajorToMinor } from "./money";
import { countdown } from "./time";

describe("money", () => {
  it("parses major units to integer minor units without floats", () => {
    expect(parseMajorToMinor("1,250,000.5")).toBe(125_000_050);
    expect(parseMajorToMinor("$0.07")).toBe(7);
    expect(parseMajorToMinor("18.2")).toBe(1820);
    expect(parseMajorToMinor("12.345")).toBeNull();
    expect(parseMajorToMinor("abc")).toBeNull();
  });

  it("round-trips and formats", () => {
    expect(minorToMajorString(312_000_000)).toBe("3120000");
    expect(minorToMajorString(1820)).toBe("18.20");
    expect(formatMoney({ amount_minor: 30_000_000, currency: "USD" }, { compact: true })).toBe("$300K");
    expect(formatBps(1500)).toBe("15%");
  });
});

describe("countdown", () => {
  const now = new Date("2026-11-07T12:00:00Z");
  it("labels urgency", () => {
    expect(countdown("2026-11-07T18:00:00Z", now)).toMatchObject({ label: "6h left", urgency: "urgent" });
    expect(countdown("2026-11-09T14:00:00Z", now)).toMatchObject({ label: "2d 2h left", urgency: "soon" });
    expect(countdown("2026-11-07T09:00:00Z", now)).toMatchObject({ label: "3h overdue", urgency: "overdue" });
  });
});
