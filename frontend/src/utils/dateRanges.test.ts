import { describe, expect, it } from "vitest";
import { localDateFilters, localDayRange } from "./dateRanges";

describe("local calendar days", () => {
  it.each([
    [2026, 8, 8],
    [2026, 2, 29],
    [2026, 9, 25],
    [2026, 11, 31],
  ])("covers the whole local day on %i/%i/%i", (year, month, day) => {
    const range = localDayRange(new Date(year, month, day, 12, 30));
    const start = new Date(range.from);
    const end = new Date(range.to);
    expect([start.getFullYear(), start.getMonth(), start.getDate()]).toEqual([year, month, day]);
    expect([end.getFullYear(), end.getMonth(), end.getDate()]).toEqual([year, month, day]);
    expect([start.getHours(), start.getMinutes(), start.getSeconds(), start.getMilliseconds()])
      .toEqual([0, 0, 0, 0]);
    expect([end.getHours(), end.getMinutes(), end.getSeconds(), end.getMilliseconds()])
      .toEqual([23, 59, 59, 999]);
    expect(range.to).toMatch(/\.999999Z$/);
    // This also runs under Europe/Amsterdam to exercise its 23/25-hour days.
    const offsetChange = end.getTimezoneOffset() - start.getTimezoneOffset();
    expect(end.getTime() - start.getTime() + 1).toBe((24 * 60 + offsetChange) * 60_000);
  });

  it("keeps either end of a date filter optional", () => {
    expect(localDateFilters("", "")).toEqual({ date_from: undefined, date_to: undefined });
    expect(localDateFilters("2026-03-29", "").date_to).toBeUndefined();
    expect(localDateFilters("", "2026-03-29").date_from).toBeUndefined();
  });

  it("uses the selected calendar dates for a range spanning an offset change", () => {
    const range = localDateFilters("2026-03-28", "2026-03-30");
    const start = new Date(range.date_from!);
    const end = new Date(range.date_to!);
    expect([start.getMonth(), start.getDate(), start.getHours()]).toEqual([2, 28, 0]);
    expect([end.getMonth(), end.getDate(), end.getHours()]).toEqual([2, 30, 23]);
    expect(range.date_to).toMatch(/\.999999Z$/);
  });
});
