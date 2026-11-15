import type { BehaviorEntry } from "../api/types";
import { dateRangeIso, formatDateLong, formatDateShort, formatDuration, to12Hour } from "../utils/time";
import { Icon, type IconName } from "./atlas/Icon";

interface RowSpec {
  key: string;
  label: string;
  icon: IconName;
  colorVar: string;
  /** Duration rows shade by logged minutes; event rows mark presence. */
  kind: "duration" | "event";
  read: (e: BehaviorEntry) => number | string | null;
  describe: (v: number | string) => string;
}

const ROWS: RowSpec[] = [
  { key: "sleep", label: "Sleep", icon: "bed", colorVar: "--sig-sleep", kind: "event", read: (e) => e.sleep_onset, describe: (v) => `sleep onset ${to12Hour(String(v))}` },
  { key: "light", label: "Light", icon: "sun", colorVar: "--sig-light", kind: "duration", read: (e) => e.morning_light_duration_minutes, describe: (v) => `morning light ${formatDuration(Number(v))}` },
  { key: "screen", label: "Screens", icon: "monitor", colorVar: "--sig-screen", kind: "duration", read: (e) => e.evening_screen_duration_minutes, describe: (v) => `evening screens ${formatDuration(Number(v))}` },
  { key: "meal", label: "Meals", icon: "cutlery", colorVar: "--sig-meal", kind: "event", read: (e) => e.last_meal_time, describe: (v) => `last meal ${to12Hour(String(v))}` },
  { key: "exercise", label: "Exercise", icon: "activity", colorVar: "--sig-exercise", kind: "event", read: (e) => e.exercise_time, describe: (v) => `exercise ${to12Hour(String(v))}` },
];

/**
 * One column per calendar day between the oldest and newest returned
 * observation, one row per signal. Days with no observation row are
 * drawn as hatched gaps -- never filled in. Duration rows (light,
 * screens) are shaded relative to the largest value in view (display
 * scaling only); event rows (sleep onset, meals, exercise) mark that a
 * time was logged, with the exact value in the tooltip.
 */
export function BehaviorHeatmap({ entries }: { entries: BehaviorEntry[] }) {
  if (entries.length === 0) {
    return (
      <div className="empty-state">
        <span className="empty-state__title">No behavior logged in this period</span>
        <p>Daily entries you log will appear here, one column per day.</p>
      </div>
    );
  }

  const byDate = new Map(entries.map((e) => [e.date, e]));
  const sortedDates = entries.map((e) => e.date).sort();
  const days = dateRangeIso(sortedDates[0], sortedDates[sortedDates.length - 1]);
  const columns = `repeat(${days.length}, minmax(0, 1fr))`;

  const maxByRow: Record<string, number> = {};
  for (const row of ROWS) {
    if (row.kind !== "duration") continue;
    const nums = entries.map((e) => row.read(e)).filter((v): v is number => typeof v === "number");
    maxByRow[row.key] = nums.length ? Math.max(...nums) : 0;
  }

  const labelEvery = Math.max(1, Math.ceil(days.length / 7));
  const observedDays = days.filter((d) => byDate.has(d)).length;

  return (
    <div>
      <div
        className="heatmap"
        role="img"
        aria-label={`Behavioral patterns from ${formatDateLong(days[0])} to ${formatDateLong(days[days.length - 1])}: ${observedDays} of ${days.length} days have logged observations.`}
      >
        {ROWS.map((row) => (
          <HeatmapRow key={row.key} row={row} days={days} byDate={byDate} columns={columns} max={maxByRow[row.key] ?? 0} />
        ))}
        <span />
        <div className="heatmap__dates" aria-hidden="true">
          {days.map((d, i) =>
            i % labelEvery === 0 || i === days.length - 1 ? (
              <span key={d} style={{ left: `${((i + 0.5) / days.length) * 100}%` }}>
                {formatDateShort(d)}
              </span>
            ) : null,
          )}
        </div>
      </div>
      <p className="small muted" style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span className="heatmap__cell heatmap__cell--empty" style={{ display: "inline-block", width: 14, height: 12 }} aria-hidden="true" />
        No observation logged · {observedDays} of {days.length} days observed. Hover a cell for the logged value.
      </p>
    </div>
  );
}

function HeatmapRow({ row, days, byDate, columns, max }: { row: RowSpec; days: string[]; byDate: Map<string, BehaviorEntry>; columns: string; max: number }) {
  return (
    <>
      <span className="heatmap__label">
        <span style={{ color: `var(${row.colorVar})`, display: "inline-flex" }}>
          <Icon name={row.icon} size={16} />
        </span>
        <span>{row.label}</span>
      </span>
      <div className="heatmap__row" style={{ gridTemplateColumns: columns }} aria-hidden="true">
        {days.map((d) => {
          const entry = byDate.get(d);
          if (!entry) return <span key={d} className="heatmap__cell heatmap__cell--empty" title={`${formatDateLong(d)} · no observation`} />;
          const value = row.read(entry);
          if (value === null || value === undefined) {
            return <span key={d} className="heatmap__cell" title={`${formatDateLong(d)} · ${row.label.toLowerCase()} not logged`} />;
          }
          const opacity = row.kind === "duration" && typeof value === "number" && max > 0 ? 0.18 + 0.82 * Math.min(1, value / max) : 0.9;
          return (
            <span key={d} className="heatmap__cell" title={`${formatDateLong(d)} · ${row.describe(value)}`}>
              <span
                className="heatmap__mark"
                style={{
                  background: `var(${row.colorVar})`,
                  opacity,
                  ...(row.kind === "duration" ? { left: 0, right: 0, top: 0, bottom: 0 } : {}),
                }}
              />
            </span>
          );
        })}
      </div>
    </>
  );
}
