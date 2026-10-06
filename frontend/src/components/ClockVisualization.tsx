import { hourToDegrees, parseClockHour, to12Hour } from "../utils/time";

export interface ClockMarker {
  key: string;
  label: string;
  value: string | null; // "HH:MM" from the API, or null if unavailable
  shape: "diamond" | "circle" | "square";
  colorVar: string; // CSS custom property name, e.g. "--color-accent"
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
export function ClockVisualization({ markers, size = 220 }: { markers: ClockMarker[]; size?: number }) {
  const center = size / 2;
  const radius = size / 2 - 28;

  const points = markers
    .map((marker) => {
      const hour = parseClockHour(marker.value);
      if (hour === null) return null;
      const angle = ((hourToDegrees(hour) - 90) * Math.PI) / 180; // -90 so 0h is at the top
      return {
        ...marker,
        hour,
        x: center + radius * Math.cos(angle),
        y: center + radius * Math.sin(angle),
      };
    })
    .filter((p): p is NonNullable<typeof p> => p !== null);

  const hourTicks = Array.from({ length: 24 }, (_, h) => h).filter((h) => h % 3 === 0);

  return (
    <div>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={describeMarkers(markers)}
      >
        <circle cx={center} cy={center} r={radius} fill="none" stroke="var(--color-border)" strokeWidth={1.5} />
        {hourTicks.map((h) => {
          const angle = ((hourToDegrees(h) - 90) * Math.PI) / 180;
          const x1 = center + (radius - 4) * Math.cos(angle);
          const y1 = center + (radius - 4) * Math.sin(angle);
          const x2 = center + (radius + 4) * Math.cos(angle);
          const y2 = center + (radius + 4) * Math.sin(angle);
          const lx = center + (radius + 16) * Math.cos(angle);
          const ly = center + (radius + 16) * Math.sin(angle);
          return (
            <g key={h} aria-hidden="true">
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--color-text-faint)" strokeWidth={1} />
              <text x={lx} y={ly} fontSize={10} fill="var(--color-text-faint)" textAnchor="middle" dominantBaseline="middle">
                {String(h).padStart(2, "0")}
              </text>
            </g>
          );
        })}
        {points.map((p) => (
          <Marker key={p.key} x={p.x} y={p.y} shape={p.shape} colorVar={p.colorVar} />
        ))}
      </svg>

      <ul style={{ listStyle: "none", margin: "12px 0 0", padding: 0, display: "flex", flexDirection: "column", gap: 6 }}>
        {markers.map((marker) => (
          <li key={marker.key} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
            <MarkerGlyph shape={marker.shape} colorVar={marker.colorVar} />
            <span style={{ color: "var(--color-text-muted)" }}>{marker.label}</span>
            <strong style={{ marginLeft: "auto" }}>{marker.value ? to12Hour(marker.value) : "—"}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Marker({ x, y, shape, colorVar }: { x: number; y: number; shape: ClockMarker["shape"]; colorVar: string }) {
  const color = `var(${colorVar})`;
  if (shape === "circle") return <circle cx={x} cy={y} r={6} fill={color} stroke="var(--color-surface)" strokeWidth={2} />;
  if (shape === "square") return <rect x={x - 5} y={y - 5} width={10} height={10} fill={color} stroke="var(--color-surface)" strokeWidth={2} />;
  return (
    <rect
      x={x - 5}
      y={y - 5}
      width={10}
      height={10}
      fill={color}
      stroke="var(--color-surface)"
      strokeWidth={2}
      transform={`rotate(45 ${x} ${y})`}
    />
  );
}

function MarkerGlyph({ shape, colorVar }: { shape: ClockMarker["shape"]; colorVar: string }) {
  const style = { width: 10, height: 10, background: `var(${colorVar})`, flexShrink: 0 } as const;
  if (shape === "circle") return <span style={{ ...style, borderRadius: "50%" }} aria-hidden="true" />;
  if (shape === "square") return <span style={style} aria-hidden="true" />;
  return <span style={{ ...style, transform: "rotate(45deg)" }} aria-hidden="true" />;
}

function describeMarkers(markers: ClockMarker[]): string {
  const parts = markers
    .filter((m) => m.value)
    .map((m) => `${m.label}: ${to12Hour(m.value)}`);
  return `24-hour clock showing ${parts.join(", ") || "no available estimates"}.`;
}
