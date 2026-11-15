import type { ReactNode } from "react";
import type { BehaviorEntry } from "../api/types";
import { formatDateLong, formatDuration, parseClockHour, to12Hour } from "../utils/time";
import { Icon, type IconName } from "./atlas/Icon";

const AXIS_HOURS = [0, 3, 6, 9, 12, 15, 18, 21, 24];

type Row =
  | { key: string; label: string; icon: IconName; colorVar: string; kind: "event"; time: string | null; caption: string }
  | { key: string; label: string; icon: IconName; colorVar: string; kind: "duration"; minutes: number | null; caption: string };

/**
 * A 24-hour horizontal observation chart for one logged day.
 *
 * Only values the behavior-history endpoint actually returns are
 * drawn: clock-time events (sleep onset, last meal, exercise) are
 * placed on the axis at their logged time; light and screen exposure
 * are returned as *durations only* (the API does not return their
 * start/end times), so they are shown as a duration with an explicit
 * "time of day not available" note rather than an invented interval.
 */
export function RhythmTimeline({ date, entry }: { date: string | null; entry: BehaviorEntry | null }) {
  const rows: Row[] = [
    { key: "sleep", label: "Sleep", icon: "bed", colorVar: "--sig-sleep", kind: "event", time: entry?.sleep_onset ?? null, caption: "Onset" },
    {
      key: "light",
      label: "Light",
      icon: "sun",
      colorVar: "--sig-light",
      kind: "duration",
      minutes: entry?.morning_light_duration_minutes ?? null,
      caption: "Morning light",
    },
    {
      key: "screen",
      label: "Screens",
      icon: "monitor",
      colorVar: "--sig-screen",
      kind: "duration",
      minutes: entry?.evening_screen_duration_minutes ?? null,
      caption: "Evening screens",
    },
    { key: "meal", label: "Meals", icon: "cutlery", colorVar: "--sig-meal", kind: "event", time: entry?.last_meal_time ?? null, caption: "Last meal" },
    { key: "exercise", label: "Exercise", icon: "activity", colorVar: "--sig-exercise", kind: "event", time: entry?.exercise_time ?? null, caption: "Exercise" },
  ];

  return (
    <section aria-labelledby="rhythm-heading">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <div className="section-label" id="rhythm-heading">
          Daily rhythm{date ? ` — ${formatDateLong(date)}` : ""}
        </div>
        {entry && <span className="small muted">As logged for this date</span>}
      </div>

      {!entry ? (
        <div className="empty-state">
          <span className="empty-state__title">{date ? "No behavior logged for this date" : "No daily result yet"}</span>
          <p>Log sleep, light, screens and meals for a day to see them laid out across the 24 hours.</p>
        </div>
      ) : (
        <div className="timeline" role="group" aria-label={describe(rows)}>
          <span className="timeline__axis-spacer" />
          <div className="timeline__axis" aria-hidden="true">
            {AXIS_HOURS.map((h) => (
              <span key={h} style={{ left: `${(h / 24) * 100}%` }}>
                {String(h).padStart(2, "0")}
              </span>
            ))}
          </div>
          <span className="timeline__value timeline__value--axis" style={{ borderTop: "none" }} />

          {rows.map((row) => (
            <TimelineRow key={row.key} row={row} />
          ))}
        </div>
      )}
    </section>
  );
}

function TimelineRow({ row }: { row: Row }) {
  const color = `var(${row.colorVar})`;
  let track: ReactNode = null;
  let value = "Not logged";

  if (row.kind === "event") {
    const hour = parseClockHour(row.time);
    if (hour !== null) {
      value = `${row.caption} ${to12Hour(row.time)}`;
      const left = `${(hour / 24) * 100}%`;
      track = (
        <>
          <span className="timeline__stem" style={{ left, background: color }} aria-hidden="true" />
          <span className="timeline__marker" style={{ left, background: color }} title={value} aria-hidden="true" />
        </>
      );
    }
  } else if (row.minutes !== null) {
    value = `${row.caption} ${formatDuration(row.minutes)}`;
    const width = `${Math.max(4, Math.min(100, (row.minutes / 240) * 100))}%`;
    track = (
      <span className="timeline__unplaced" title={`${value} · time of day not available`}>
        <span style={{ width: 90, display: "inline-flex" }} aria-hidden="true">
          <span className="timeline__duration-bar" style={{ width, background: color }} />
        </span>
        <span>time of day not available</span>
      </span>
    );
  }

  return (
    <>
      <span className="timeline__label">
        <span style={{ color, display: "inline-flex" }}>
          <Icon name={row.icon} size={17} />
        </span>
        {row.label}
      </span>
      <div className="timeline__track">{track}</div>
      <span className="timeline__value">{value}</span>
    </>
  );
}

function describe(rows: Row[]): string {
  const parts = rows.map((row) => {
    if (row.kind === "event") return row.time ? `${row.caption} at ${to12Hour(row.time)}` : `${row.label} not logged`;
    return row.minutes !== null ? `${row.caption} ${formatDuration(row.minutes)}` : `${row.label} not logged`;
  });
  return `Logged behavior across the day: ${parts.join("; ")}.`;
}
