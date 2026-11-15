import { hourLabel, hourTo12Hour, unwrapHourSeries } from "../utils/time";

export type JourneySeriesKind = "clock" | "score" | "amount";

/**
 * A compact day-indexed (Day 1..N) line chart for the 30-day journey.
 * `values[i]` is the persisted value for day i+1, or null where none
 * exists (warm-up days have no estimate; a missing observation stays a
 * gap -- never interpolated). Clock series are unwrapped for display so
 * a run crossing midnight stays continuous (utils/time.ts). Purely
 * presentational: plots API values, computes nothing.
 */
export function JourneyChart({
  title,
  values,
  kind,
  unit = "",
  colorVar,
  selectedIndex,
  warmupCount,
  onSelect,
}: {
  title: string;
  values: Array<number | null>;
  kind: JourneySeriesKind;
  unit?: string;
  colorVar: string;
  selectedIndex: number;
  warmupCount: number;
  onSelect?: (index: number) => void;
}) {
  const width = 520;
  const height = 176;
  const left = 46;
  const right = 10;
  const top = 12;
  const bottom = 26;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const n = values.length;

  const series = kind === "clock" ? unwrapHourSeries(values) : values;
  const present = series.filter((v): v is number => v !== null);

  let yMin = 0;
  let yMax = 100;
  let ticks = [0, 50, 100];
  if (kind === "clock" && present.length) {
    yMin = Math.floor(Math.min(...present) - 0.25);
    yMax = Math.ceil(Math.max(...present) + 0.25);
    const step = yMax - yMin > 6 ? 2 : 1;
    ticks = [];
    for (let t = yMin; t <= yMax; t += step) ticks.push(t);
  } else if (kind === "amount" && present.length) {
    const top10 = Math.max(10, Math.ceil(Math.max(...present) / 10) * 10);
    yMax = top10;
    ticks = [0, Math.round(top10 / 2), top10];
  }
  const span = yMax - yMin || 1;
  const xAt = (i: number) => left + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const yAt = (v: number) => top + plotH - ((v - yMin) / span) * plotH;

  const format = (v: number) => (kind === "clock" ? hourTo12Hour(v) : `${Math.round(v)}${unit ? ` ${unit}` : ""}`);
  const tickText = (t: number) => (kind === "clock" ? hourLabel(t) : String(t));

  let path = "";
  series.forEach((v, i) => {
    if (v === null) return;
    const prevPresent = i > 0 && series[i - 1] !== null;
    path += `${prevPresent ? "L" : "M"}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)} `;
  });

  const selectedValue = series[selectedIndex];
  const firstDay = present.length ? series.findIndex((v) => v !== null) + 1 : null;
  const label = present.length
    ? `${title}: ${present.length} of ${n} days have a value, from day ${firstDay}. Selected day ${selectedIndex + 1}: ${selectedValue !== null && selectedValue !== undefined ? format(selectedValue) : "no value"}.`
    : `${title}: no values recorded.`;

  return (
    <figure className="journey-chart">
      <figcaption>
        <span className="section-label" style={{ marginBottom: 0 }}>
          {title}
        </span>
        <span className="small muted">
          Day {selectedIndex + 1}: <strong style={{ color: "var(--ink)" }}>{selectedValue !== null && selectedValue !== undefined ? format(selectedValue) : "—"}</strong>
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
        <g aria-hidden="true">
          {warmupCount > 0 && (
            <>
              <rect x={left} y={top} width={xAt(warmupCount - 0.5) - left} height={plotH} fill="var(--sand-soft)" opacity={0.55} />
              <text x={left + 4} y={top + 11} fontSize={9.5} fill="var(--brown)" fontFamily="var(--font-ui)">
                warm-up
              </text>
            </>
          )}
          {ticks.map((t) => (
            <g key={t}>
              <line x1={left} x2={width - right} y1={yAt(t)} y2={yAt(t)} stroke="var(--sand)" strokeWidth={0.7} strokeDasharray="2 4" />
              <text x={left - 6} y={yAt(t)} fontSize={10} fill="var(--brown)" textAnchor="end" dominantBaseline="central" fontFamily="var(--font-ui)">
                {tickText(t)}
              </text>
            </g>
          ))}
          {[1, 7, 14, 21, 30].filter((d) => d <= n).map((d) => (
            <text key={d} x={xAt(d - 1)} y={height - 8} fontSize={10} fill="var(--ink)" textAnchor="middle" fontFamily="var(--font-ui)">
              {d}
            </text>
          ))}
          <line x1={xAt(selectedIndex)} x2={xAt(selectedIndex)} y1={top} y2={top + plotH} stroke="var(--rust)" strokeWidth={1} strokeOpacity={0.7} />
        </g>
        <path d={path} fill="none" stroke={`var(${colorVar})`} strokeWidth={1.6} strokeLinejoin="round" aria-hidden="true" />
        {series.map((v, i) =>
          v === null ? null : (
            <circle
              key={i}
              cx={xAt(i)}
              cy={yAt(v)}
              r={i === selectedIndex ? 4.6 : 2.8}
              fill={i === selectedIndex ? "var(--rust)" : `var(${colorVar})`}
              stroke="var(--parchment)"
              strokeWidth={1}
              style={{ cursor: onSelect ? "pointer" : undefined }}
              onClick={onSelect ? () => onSelect(i) : undefined}
              aria-hidden="true"
            >
              <title>{`Day ${i + 1} · ${format(v)}`}</title>
            </circle>
          ),
        )}
      </svg>
    </figure>
  );
}
