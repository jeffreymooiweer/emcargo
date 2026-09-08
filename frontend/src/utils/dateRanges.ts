/** Local calendar bounds for the API's inclusive, microsecond-precision filters. */
export function localDayRange(now = new Date()): { from: string; to: string } {
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  // Advancing the calendar date preserves 23/25-hour daylight-saving days.
  // JavaScript stores milliseconds; the database can store microseconds.
  const lastMillisecond = new Date(next.getTime() - 1).toISOString();
  return { from: start.toISOString(), to: lastMillisecond.replace(/\.999Z$/, ".999999Z") };
}

/** Convert native date-input values to the same UTC bounds used by the overview. */
export function localDateFilters(from: string, to: string): { date_from?: string; date_to?: string } {
  // A bare YYYY-MM-DD parses as UTC; a local time suffix preserves the
  // calendar date selected by the user, also in timezones west of UTC.
  return {
    date_from: from ? localDayRange(new Date(`${from}T12:00:00`)).from : undefined,
    date_to: to ? localDayRange(new Date(`${to}T12:00:00`)).to : undefined,
  };
}
