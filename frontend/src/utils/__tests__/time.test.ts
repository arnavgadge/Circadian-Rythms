import { describe, expect, it } from "vitest";
import { circularDiffHours, parseClockHour, to12Hour, unwrapHourSeries } from "../time";

describe("parseClockHour", () => {
  it("parses HH:MM into a decimal hour", () => {
    expect(parseClockHour("23:48")).toBeCloseTo(23.8, 1);
    expect(parseClockHour("00:10")).toBeCloseTo(0.1667, 3);
  });

  it("returns null for missing or malformed input", () => {
    expect(parseClockHour(null)).toBeNull();
    expect(parseClockHour(undefined)).toBeNull();
    expect(parseClockHour("not a time")).toBeNull();
  });
});

describe("circularDiffHours", () => {
  it("treats 23:50 -> 00:10 as +20 minutes, not -23h40m", () => {
    const diff = circularDiffHours(0.1667, 23.8333);
    expect(diff).toBeCloseTo(20 / 60, 2);
  });
});

// --- 15. Midnight-crossing trajectory ---
describe("unwrapHourSeries", () => {
  it("renders a midnight-crossing trajectory as continuous, not discontinuous", () => {
    const unwrapped = unwrapHourSeries([23.8333, 0.0833, 0.3333]); // 23:50, 00:05, 00:20
    expect(unwrapped[0]).toBeCloseTo(23.8333, 3);
    expect(unwrapped[1]!).toBeGreaterThan(unwrapped[0]!);
    expect(unwrapped[2]!).toBeGreaterThan(unwrapped[1]!);
    expect(unwrapped[2]! - unwrapped[0]!).toBeCloseTo(0.5, 1); // 30 minutes of real drift
  });

  it("passes null entries through as gaps rather than guessing", () => {
    const unwrapped = unwrapHourSeries([21.0, null, 21.5]);
    expect(unwrapped[1]).toBeNull();
    expect(unwrapped[2]).not.toBeNull();
  });
});

describe("to12Hour", () => {
  it("formats a 24h string as a friendly 12h clock", () => {
    expect(to12Hour("23:48")).toBe("11:48 PM");
    expect(to12Hour("00:10")).toBe("12:10 AM");
    expect(to12Hour("12:00")).toBe("12:00 PM");
  });
});
