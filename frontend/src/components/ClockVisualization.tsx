import type { ReactNode } from "react";
import { circularDiffHours, hourToDegrees, parseClockHour, to12Hour } from "../utils/time";
import { ClockCenterScene } from "./atlas/Illustrations";

export interface ClockMarker {
  key: string;
  label: string;
  value: string | null; // "HH:MM" from the API, or null if unavailable
  shape: "diamond" | "circle" | "square";
  colorVar: string; // CSS custom property name, e.g. "--rust"
}

/** Optional arc drawn along the 24h track between two marker keys
 * (both values supplied by the API -- e.g. ideal vs. actual sleep
 * onset). Purely positional: the arc spans whichever way round the
 * circle is shorter, so it never wraps the long way past midnight. */
export interface ClockArc {
  fromKey: string;
  toKey: string;
  colorVar: string;
  label: string;
}

/**
 * A 24-hour circular clock face showing already-computed values from
 * the API (estimated biological clock, ideal sleep onset, actual
 * sleep onset) as markers around the circle. Renders nothing new --
 * every position comes directly from a supplied "HH:MM" string; this
 * component only converts that string to an angle for display.
 *
 * Midnight is handled correctly because each marker is placed by its
 * own absolute clock position on the circle (0-24h mapped to 360
 * degrees) -- there is no linear axis to "cross," so 23:50 and 00:10
 * naturally sit right next to each other.
 */
export function ClockVisualization({
  markers,
  size = 320,
  arc,
  children,
}: {
  markers: ClockMarker[];
  size?: number;
  arc?: ClockArc;
  children?: ReactNode;
}) {
  const pad = 22;
  const center = size / 2;
  const outer = size / 2 - pad;
  const track = outer - 11;
  const inner = outer - 24;

  const polar = (hour: number, rad: number) => {
    const angle = ((hourToDegrees(hour) - 90) * Math.PI) / 180; // -90 so 0h is at the top
    return { x: center + rad * Math.cos(angle), y: center + rad * Math.sin(angle) };
  };

  const points = markers
    .map((marker) => {
      const hour = parseClockHour(marker.value);
      if (hour === null) return null;
      return { ...marker, hour, ...polar(hour, track) };
    })
    .filter((p): p is NonNullable<typeof p> => p !== null);

  const ticks = Array.from({ length: 96 }, (_, i) => i / 4); // every 15 minutes
  const labelHours = [0, 3, 6, 9, 12, 15, 18, 21];
  const hand = points.find((p) => p.key === "dlmo");

  let arcPath: string | null = null;
  if (arc) {
    const a = points.find((p) => p.key === arc.fromKey);
    const b = points.find((p) => p.key === arc.toKey);
    if (a && b) {
      const sweepHours = circularDiffHours(b.hour, a.hour);
      if (Math.abs(sweepHours) > 0.02) {
        const start = polar(a.hour, track);
        const end = polar(b.hour, track);
        const sweepFlag = sweepHours > 0 ? 1 : 0;
        arcPath = `M ${start.x} ${start.y} A ${track} ${track} 0 0 ${sweepFlag} ${end.x} ${end.y}`;
      }
    }
  }

  return (
    <div className="clock-viz">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={describeMarkers(markers)}>
        <circle cx={center} cy={center} r={outer} fill="var(--parchment)" stroke="var(--ink)" strokeWidth={1.2} />
        <circle cx={center} cy={center} r={track} fill="none" stroke="var(--sand-soft)" strokeWidth={14} />
        <ClockCenterScene cx={center} cy={center} r={inner} />
        <circle cx={center} cy={center} r={inner} fill="none" stroke="var(--ink)" strokeOpacity={0.5} strokeWidth={0.8} />

        <g aria-hidden="true">
          {ticks.map((h) => {
            const major = h % 3 === 0;
            const hourly = Number.isInteger(h);
            const len = major ? 8 : hourly ? 5 : 2.5;
            const p1 = polar(h, outer);
            const p2 = polar(h, outer - len);
            return (
              <line
                key={h}
                x1={p1.x}
                y1={p1.y}
                x2={p2.x}
                y2={p2.y}
                stroke="var(--ink)"
                strokeOpacity={major ? 0.85 : hourly ? 0.5 : 0.3}
                strokeWidth={major ? 1.3 : 0.8}
              />
            );
          })}
          {labelHours.map((h) => {
            const p = polar(h, outer + 12);
            return (
              <text
                key={h}
                x={p.x}
                y={p.y}
                fontSize={12}
                fontFamily="var(--font-display)"
                fontWeight={600}
                fill="var(--ink)"
                textAnchor="middle"
                dominantBaseline="central"
              >
                {String(h).padStart(2, "0")}
              </text>
            );
          })}
        </g>

        {arcPath && arc && (
          <path d={arcPath} fill="none" stroke={`var(${arc.colorVar})`} strokeWidth={14} strokeOpacity={0.55} aria-hidden="true" />
        )}

        {hand && (
          <line
            x1={center}
            y1={center}
            x2={hand.x}
            y2={hand.y}
            stroke={`var(${hand.colorVar})`}
            strokeWidth={1.2}
            strokeOpacity={0.9}
            aria-hidden="true"
          />
        )}
        {hand && <circle cx={center} cy={center} r={3} fill={`var(${hand.colorVar})`} aria-hidden="true" />}

        {points.map((p) => (
          <Marker key={p.key} x={p.x} y={p.y} shape={p.shape} colorVar={p.colorVar} />
        ))}
      </svg>

      <div className="legend-block">
        <ul className="legend">
          {markers.map((marker) => (
            <li key={marker.key}>
              <MarkerGlyph shape={marker.shape} colorVar={marker.colorVar} />
              <span className="muted">{marker.label}</span>
              <strong>{marker.value ? to12Hour(marker.value) : "—"}</strong>
            </li>
          ))}
          {arc && arcPath && (
            <li>
              <span className="signal-swatch" style={{ width: 10, height: 10, background: `var(${arc.colorVar})`, opacity: 0.55 }} aria-hidden="true" />
              <span className="muted small">{arc.label}</span>
            </li>
          )}
        </ul>
        {children}
      </div>
    </div>
  );
}

function Marker({ x, y, shape, colorVar }: { x: number; y: number; shape: ClockMarker["shape"]; colorVar: string }) {
  const color = `var(${colorVar})`;
  if (shape === "circle") return <circle cx={x} cy={y} r={6} fill={color} stroke="var(--parchment)" strokeWidth={2} />;
  if (shape === "square") return <rect x={x - 5} y={y - 5} width={10} height={10} fill={color} stroke="var(--parchment)" strokeWidth={2} />;
  return <rect x={x - 6} y={y - 6} width={12} height={12} fill={color} stroke="var(--parchment)" strokeWidth={2} transform={`rotate(45 ${x} ${y})`} />;
}

function MarkerGlyph({ shape, colorVar }: { shape: ClockMarker["shape"]; colorVar: string }) {
  const style = { width: 10, height: 10, background: `var(${colorVar})`, flexShrink: 0, display: "inline-block" } as const;
  if (shape === "circle") return <span style={{ ...style, borderRadius: "50%" }} aria-hidden="true" />;
  if (shape === "square") return <span style={style} aria-hidden="true" />;
  return <span style={{ ...style, width: 9, height: 9, transform: "rotate(45deg)" }} aria-hidden="true" />;
}

function describeMarkers(markers: ClockMarker[]): string {
  const parts = markers.filter((m) => m.value).map((m) => `${m.label}: ${to12Hour(m.value)}`);
  return `24-hour clock showing ${parts.join(", ") || "no available estimates"}.`;
}
