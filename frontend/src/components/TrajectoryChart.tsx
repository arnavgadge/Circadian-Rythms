import { useId, useMemo, useState } from "react";
import type { CircadianHistoryEntry } from "../api/types";
import { formatDateLong, formatDateShort, hourLabel, hourTo12Hour, parseClockHour, unwrapHourSeries } from "../utils/time";

type Metric = "clock" | "alignment" | "confidence";

const METRIC_LABELS: Record<Metric, string> = {
  clock: "Estimated biological clock",
  alignment: "Alignment score",
  confidence: "Confidence",
};

/**
 * A time-series chart over the circadian history endpoint. The
 * "clock" metric is drawn on an **unwrapped** trajectory so a
 * midnight-crossing run (23:50 -> 00:10) renders as a continuous
 * line rather than a discontinuous jump -- see utils/time.ts. Every
 * plotted value comes directly from the API; nothing is computed
 * here beyond that display-only unwrap and pixel geometry.
 *
 * `entries` arrive newest-first (API order) and are plotted oldest
 * to newest. The time range is owned by the parent page, which
 * re-requests the history endpoint when it changes.
 */
export function TrajectoryChart({ entries }: { entries: CircadianHistoryEntry[] }) {
  const [metric, setMetric] = useState<Metric>("clock");
  const ordered = useMemo(() => entries.slice().reverse(), [entries]);

  if (entries.length === 0) {
    return (
      <section aria-labelledby="history-heading">
        <div className="section-label" id="history-heading">
          Estimated biological clock
        </div>
        <p className="muted">No history is available yet. Run a few days of daily inference to see your trend.</p>
      </section>
    );
  }

  return (
    <section aria-labelledby="history-heading">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 6 }}>
        <div className="section-label" id="history-heading" style={{ marginBottom: 0 }}>
          {METRIC_LABELS[metric]}
          {metric === "clock" ? " (DLMO, model-based)" : ""}
        </div>
        <div role="tablist" aria-label="Metric" className="segmented segmented--quiet">
          {(Object.keys(METRIC_LABELS) as Metric[]).map((key) => (
            <button key={key} type="button" role="tab" aria-selected={metric === key} onClick={() => setMetric(key)}>
              {METRIC_LABELS[key]}
            </button>
          ))}
        </div>
      </div>
      <Chart entries={ordered} metric={metric} />
    </section>
  );
}

interface Pt {
  x: number;
  y: number;
  value: number;
  date: string;
}

function Chart({ entries, metric }: { entries: CircadianHistoryEntry[]; metric: Metric }) {
  const gradientId = useId().replace(/:/g, "");
  const width = 900;
  const height = 280;
  const left = 56;
  const right = 18;
  const top = 16;
  const bottom = 34;
  const plotW = width - left - right;
  const plotH = height - top - bottom;

  const rawValues =
    metric === "clock"
      ? entries.map((e) => parseClockHour(e.biological_clock))
      : metric === "alignment"
        ? entries.map((e) => e.alignment_score)
        : entries.map((e) => e.confidence_score);

  const values = metric === "clock" ? unwrapHourSeries(rawValues) : rawValues;
  const present = values.filter((v): v is number => v !== null);

  if (present.length === 0) {
    return <p className="muted" style={{ marginTop: 16 }}>No {METRIC_LABELS[metric].toLowerCase()} data in this range.</p>;
  }

  // Axis domain: clock values span their own (unwrapped) range padded
  // to whole hours; scores use their fixed 0-100 scale.
  let yMin: number;
  let yMax: number;
  let ticks: number[];
  if (metric === "clock") {
    yMin = Math.floor(Math.min(...present) - 0.5);
    yMax = Math.ceil(Math.max(...present) + 0.5);
    const stepHours = yMax - yMin > 8 ? 2 : 1;
    ticks = [];
    for (let t = yMin; t <= yMax; t += stepHours) ticks.push(t);
  } else {
    yMin = 0;
    yMax = 100;
    ticks = [0, 25, 50, 75, 100];
  }
  const span = yMax - yMin || 1;

  const xAt = (index: number) => left + (entries.length === 1 ? plotW / 2 : (index / (entries.length - 1)) * plotW);
  const yAt = (v: number) => top + plotH - ((v - yMin) / span) * plotH;

  const points: Array<Pt | null> = values.map((value, index) => (value === null ? null : { x: xAt(index), y: yAt(value), value, date: entries[index].date }));

  const segments: Pt[][] = [];
  let current: Pt[] = [];
  for (const p of points) {
    if (p === null) {
      if (current.length) segments.push(current);
      current = [];
    } else {
      current.push(p);
    }
  }
  if (current.length) segments.push(current);

  const linePath = segments.map((seg) => seg.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")).join(" ");
  const areaPath = segments
    .filter((seg) => seg.length > 1)
    .map((seg) => `M${seg[0].x},${top + plotH} ${seg.map((p) => `L${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")} L${seg[seg.length - 1].x},${top + plotH} Z`)
    .join(" ");

  const formatValue = (value: number) => (metric === "clock" ? hourTo12Hour(value) : Math.round(value).toString());
  const tickLabel = (t: number) => (metric === "clock" ? hourLabel(t) : String(t));

  const labelEvery = Math.max(1, Math.ceil(entries.length / 7));
  const dateLabels = entries.map((e, i) => ({ i, date: e.date })).filter(({ i }) => i % labelEvery === 0 || i === entries.length - 1);

  return (
    <div className="chart-frame">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${METRIC_LABELS[metric]} over the selected range, from ${formatValue(present[0])} to ${formatValue(present[present.length - 1])}.`}
        style={{ marginTop: 10 }}
      >
        <defs>
          <linearGradient id={`${gradientId}-area`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--teal)" stopOpacity="0.16" />
            <stop offset="100%" stopColor="var(--teal)" stopOpacity="0" />
          </linearGradient>
        </defs>

        <g aria-hidden="true">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={left} x2={width - right} y1={yAt(t)} y2={yAt(t)} stroke="var(--sand)" strokeWidth={0.8} strokeDasharray={t === yMin ? undefined : "2 4"} />
              <text x={left - 10} y={yAt(t)} fontSize={11} fill="var(--brown)" textAnchor="end" dominantBaseline="central" fontFamily="var(--font-ui)">
                {tickLabel(t)}
              </text>
            </g>
          ))}
          {dateLabels.map(({ i, date }) => (
            <g key={date}>
              <line x1={xAt(i)} x2={xAt(i)} y1={top + plotH} y2={top + plotH + 4} stroke="var(--brown)" strokeWidth={0.8} />
              <text x={xAt(i)} y={top + plotH + 18} fontSize={11} fill="var(--ink)" textAnchor="middle" fontFamily="var(--font-ui)">
                {formatDateShort(date)}
              </text>
            </g>
          ))}
        </g>

        {areaPath && <path d={areaPath} fill={`url(#${gradientId}-area)`} />}
        <path d={linePath} fill="none" stroke="var(--evergreen)" strokeWidth={1.6} strokeLinejoin="round" />
        {points.map((p, i) =>
          p === null ? null : (
            <circle key={i} cx={p.x} cy={p.y} r={3.2} fill="var(--evergreen)" stroke="var(--parchment)" strokeWidth={1.2}>
              <title>{`${formatDateLong(p.date)} · ${formatValue(p.value)}`}</title>
            </circle>
          ),
        )}
      </svg>
    </div>
  );
}
