/**
 * Circular-time display helpers -- **visualization only**. The API
 * always supplies the actual estimated values (DLMO, targets,
 * alignment, etc.); nothing here computes or infers a circadian
 * value. This module only converts an already-given "HH:MM" string
 * into angles/continuous trajectories so charts render correctly
 * across midnight (see docs/ui_architecture.md "Chart behavior").
 */

/** "23:48" -> 23.8, "00:10" -> 0.1667. Returns null for anything else. */
export function parseClockHour(value: string | null | undefined): number | null {
  if (!value) return null;
  const match = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (Number.isNaN(hour) || Number.isNaN(minute) || hour > 23 || minute > 59) return null;
  return hour + minute / 60;
}

/** A clock hour (0-24) -> degrees on a 24-hour clock face, 0 = 12
 * o'clock position (top), clockwise. */
export function hourToDegrees(hour: number): number {
  return (hour / 24) * 360;
}

/** The shortest signed distance (hours) from `a` to `b` around a
 * 24-hour circle, in (-12, 12] -- e.g. 23:50 -> 00:10 is +0.33h, never
 * -23.67h. The one authoritative circular-diff helper for the UI. */
export function circularDiffHours(a: number, b: number): number {
  let diff = ((a - b + 12) % 24) - 12;
  if (diff <= -12) diff += 24;
  return diff;
}

/**
 * Unwraps a chronological series of clock hours into a continuous
 * (non-wrapping) trajectory for line-chart rendering -- 23:50, 00:05,
 * 00:20 becomes [23.83, 24.08, 24.33], a smoothly increasing series,
 * instead of a discontinuous drop back to ~0. Entries with a null
 * hour are passed through as null (break in the line) rather than
 * guessed.
 */
export function unwrapHourSeries(hours: Array<number | null>): Array<number | null> {
  const result: Array<number | null> = [];
  let lastUnwrapped: number | null = null;

  for (const hour of hours) {
    if (hour === null) {
      result.push(null);
      continue;
    }
    if (lastUnwrapped === null) {
      result.push(hour);
    } else {
      const step = circularDiffHours(hour, ((lastUnwrapped % 24) + 24) % 24);
      result.push(lastUnwrapped + step);
    }
    lastUnwrapped = result[result.length - 1] as number;
  }
  return result;
}

/** "23:48" -> "11:48 PM" for a friendlier consumer display; falls
 * back to the raw string if it isn't a recognizable HH:MM value. */
export function to12Hour(value: string | null | undefined): string {
  const hour = parseClockHour(value);
  if (hour === null || !value) return value ?? "--";
  const totalMinutes = Math.round(hour * 60);
  const h24 = Math.floor(totalMinutes / 60) % 24;
  const m = totalMinutes % 60;
  const suffix = h24 < 12 ? "AM" : "PM";
  let h12 = h24 % 12;
  if (h12 === 0) h12 = 12;
  return `${h12}:${String(m).padStart(2, "0")} ${suffix}`;
}
