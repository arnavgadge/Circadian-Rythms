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

/* ---------- Calendar-date display helpers (formatting only) ---------- */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** Today's date in the browser's local timezone, as "YYYY-MM-DD". */
export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function parseIsoDate(iso: string): [number, number, number] | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return null;
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

/** Shift a "YYYY-MM-DD" date by whole days (timezone-safe). */
export function addDaysIso(iso: string, days: number): string {
  const parts = parseIsoDate(iso);
  if (!parts) return iso;
  const dt = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2] + days));
  return dt.toISOString().slice(0, 10);
}

/** "2026-11-08" -> "08 Nov 2026". */
export function formatDateLong(iso: string | null | undefined): string {
  if (!iso) return "—";
  const parts = parseIsoDate(iso);
  if (!parts) return iso;
  return `${pad2(parts[2])} ${MONTHS[parts[1] - 1]} ${parts[0]}`;
}

/** "2026-11-08" -> "08 Nov". */
export function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const parts = parseIsoDate(iso);
  if (!parts) return iso;
  return `${pad2(parts[2])} ${MONTHS[parts[1] - 1]}`;
}

/** Inclusive list of consecutive "YYYY-MM-DD" dates from `start` to `end`. */
export function dateRangeIso(start: string, end: string): string[] {
  const out: string[] = [];
  let cursor = start;
  for (let guard = 0; cursor <= end && guard < 400; guard += 1) {
    out.push(cursor);
    cursor = addDaysIso(cursor, 1);
  }
  return out;
}

/** 198 -> "3h 18m"; 42 -> "42 min". Display formatting of a logged duration. */
export function formatDuration(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || Number.isNaN(minutes)) return "—";
  const total = Math.round(minutes);
  if (total < 60) return `${total} min`;
  const h = Math.floor(total / 60);
  const m = total % 60;
  return m === 0 ? `${h}h` : `${h}h ${String(m).padStart(2, "0")}m`;
}

/** An (optionally unwrapped) hour value -> "23:00"-style 24h axis label. */
export function hourLabel(hour: number): string {
  const wrapped = ((hour % 24) + 24) % 24;
  const totalMinutes = Math.round(wrapped * 60) % (24 * 60);
  return `${pad2(Math.floor(totalMinutes / 60))}:${pad2(totalMinutes % 60)}`;
}

/** An (optionally unwrapped) hour value -> "11:48 PM". */
export function hourTo12Hour(hour: number): string {
  return to12Hour(hourLabel(hour));
}

/** Display formatting for an API `target_display` / `actual_display`
 * string: "HH:MM" -> "11:30 PM"; a numeric string -> rounded for
 * reading ("30.81" -> "31"); anything else is shown as given. */
export function formatTargetDisplay(value: string | null | undefined): string {
  if (!value) return "—";
  const trimmed = value.trim();
  if (/^\d{1,2}:\d{2}$/.test(trimmed)) return to12Hour(trimmed);
  const n = Number(trimmed);
  if (trimmed !== "" && Number.isFinite(n)) return String(Math.round(n));
  return value;
}
