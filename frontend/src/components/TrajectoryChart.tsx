import { useMemo, useState } from "react";
import type { CircadianHistoryEntry } from "../api/types";
import { parseClockHour, unwrapHourSeries, to12Hour } from "../utils/time";

type Metric = "clock" | "alignment" | "confidence";

const METRIC_LABELS: Record<Metric, string> = {
  clock: "Estimated biological clock",
  alignment: "Alignment score",
  confidence: "Confidence",
};

const RANGE_OPTIONS = [
  { label: "7 days", days: 7 },
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
];

/**
 * A time-series chart over the circadian history endpoint. The
 * "clock" metric is drawn on an **unwrapped** trajectory so a
 * midnight-crossing run (23:50 -> 00:10) renders as a continuous
 * line rather than a discontinuous jump -- see utils/time.ts. Every
 * plotted value comes directly from the API; nothing is computed
 * here beyond that display-only unwrap.
 */
export function TrajectoryChart({ entries }: { entries: CircadianHistoryEntry[] }) {
  const [metric, setMetric] = useState<Metric>("clock");
  const [rangeDays, setRangeDays] = useState(30);

  const visible = useMemo(() => entries.slice(0, rangeDays).slice().reverse(), [entries, rangeDays]);

  if (entries.length === 0) {
    return (
      <section className="card" aria-labelledby="history-heading">
        <div className="section-label" id="history-heading">
          Progress
        </div>
        <p style={{ color: "var(--color-text-muted)" }}>No history is available yet. Run a few days of daily inference to see your trend.</p>
      </section>
    );
  }

  return (
    <section className="card" aria-labelledby="history-heading">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div className="section-label" id="history-heading" style={{ marginBottom: 0 }}>
          Progress
        </div>
        <div role="group" aria-label="Time range" style={{ display: "flex", gap: 6 }}>
          {RANGE_OPTIONS.map((option) => (
            <button
              key={option.days}
              type="button"
              className="button button--secondary"
              aria-pressed={rangeDays === option.days}
              style={{ padding: "4px 10px", fontSize: 12, background: rangeDays === option.days ? "var(--color-accent-soft)" : undefined }}
              onClick={() => setRangeDays(option.days)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div role="tablist" aria-label="Metric" style={{ display: "flex", gap: 6, marginTop: 12 }}>
        {(Object.keys(METRIC_LABELS) as Metric[]).map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={metric === key}
            className="button button--secondary"
            style={{ padding: "4px 10px", fontSize: 12, background: metric === key ? "var(--color-accent-soft)" : undefined }}
            onClick={() => setMetric(key)}
          >
            {METRIC_LABELS[key]}
          </button>
        ))}
      </div>

      <Chart entries={visible} metric={metric} />
    </section>
  );
}

function Chart({ entries, metric }: { entries: CircadianHistoryEntry[]; metric: Metric }) {
  const width = 640;
  const height = 220;
  const padding = 32;

  const rawValues =
    metric === "clock"
      ? entries.map((e) => parseClockHour(e.biological_clock))
      : metric === "alignment"
        ? entries.map((e) => e.alignment_score)
        : entries.map((e) => e.confidence_score);

  const values = metric === "clock" ? unwrapHourSeries(rawValues) : rawValues;
  const present = values.filter((v): v is number => v !== null);

  if (present.length === 0) {
    return <p style={{ color: "var(--color-text-muted)", marginTop: 16 }}>No {METRIC_LABELS[metric].toLowerCase()} data in this range.</p>;
  }

  const min = Math.min(...present);
  const max = Math.max(...present);
  const span = max - min || 1;

  const points = values.map((value, index) => {
    if (value === null) return null;
    const x = padding + (index / Math.max(1, entries.length - 1)) * (width - padding * 2);
    const y = height - padding - ((value - min) / span) * (height - padding * 2);
    return { x, y, value, date: entries[index].date };
  });

  const path = points
    .map((p, i) => {
      if (p === null) return null;
      const isSubpathStart = i === 0 || points[i - 1] === null;
      return `${isSubpathStart ? "M" : "L"}${p.x},${p.y}`;
    })
    .filter((segment): segment is string => segment !== null)
    .join(" ");

  const formatValue = (value: number) => (metric === "clock" ? to12Hour(`${Math.floor(((value % 24) + 24) % 24)}:${String(Math.round((value % 1) * 60)).padStart(2, "0")}`) : Math.round(value).toString());

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${METRIC_LABELS[metric]} over the selected range, from ${formatValue(present[0])} to ${formatValue(present[present.length - 1])}.`}
      style={{ marginTop: 16 }}
    >
      <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="var(--color-border)" />
      <path d={path} fill="none" stroke="var(--color-accent)" strokeWidth={2} />
      {points.map((p, i) =>
        p === null ? null : <circle key={i} cx={p.x} cy={p.y} r={2.5} fill="var(--color-accent)" />,
      )}
      <text x={padding} y={height - padding + 16} fontSize={11} fill="var(--color-text-faint)">
        {entries[0]?.date}
      </text>
      <text x={width - padding} y={height - padding + 16} fontSize={11} fill="var(--color-text-faint)" textAnchor="end">
        {entries[entries.length - 1]?.date}
      </text>
    </svg>
  );
}
