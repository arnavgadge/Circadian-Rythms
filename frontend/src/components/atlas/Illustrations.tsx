import { useId, useMemo } from "react";

/**
 * Reusable "circadian cartography" illustrations: layered mountain
 * silhouettes with thin contour lines, sun discs, moon phases and
 * orbit lines. Entirely decorative (aria-hidden) and fully
 * deterministic -- every ridge is a fixed sum of sines, so the artwork
 * never changes between renders and never encodes participant data.
 */

interface Ridge {
  base: number; // baseline y of the ridge
  amp: number; // ridge amplitude
  freqs: [number, number, number];
  phases: [number, number, number];
  valley?: number; // extra depth pushed into the horizontal centre (frames content)
  fill: string;
  contour?: string; // contour line colour
  contours?: number;
  gap?: number;
}

const TAU = Math.PI * 2;

function ridgeY(x: number, w: number, r: Ridge, k: number): number {
  const t = x / w;
  const wave =
    0.55 * Math.sin(t * r.freqs[0] * TAU + r.phases[0]) +
    0.3 * Math.sin(t * r.freqs[1] * TAU + r.phases[1]) +
    0.15 * Math.sin(t * r.freqs[2] * TAU + r.phases[2]);
  const valley = r.valley ? r.valley * Math.exp(-Math.pow((t - 0.5) / 0.19, 2)) : 0;
  const damp = Math.max(0.15, 1 - k * 0.08);
  return r.base + valley + r.amp * damp * wave + k * (r.gap ?? 7);
}

function linePoints(w: number, r: Ridge, k: number, step: number): string {
  const pts: string[] = [];
  for (let x = 0; x <= w + 0.01; x += step) {
    pts.push(`${x.toFixed(1)},${ridgeY(x, w, r, k).toFixed(1)}`);
  }
  return pts.join(" L");
}

function MountainLayers({ width, height, ridges, step = 6 }: { width: number; height: number; ridges: Ridge[]; step?: number }) {
  const id = useId().replace(/:/g, "");
  const shapes = useMemo(
    () =>
      ridges.map((r) => ({
        r,
        fill: `M0,${height} L${linePoints(width, r, 0, step)} L${width},${height} Z`,
        contours: Array.from({ length: r.contours ?? 0 }, (_, i) => `M${linePoints(width, r, i + 1, step)}`),
      })),
    [ridges, width, height, step],
  );

  return (
    <g>
      {shapes.map((s, i) => (
        <g key={i}>
          <clipPath id={`${id}-c${i}`}>
            <path d={s.fill} />
          </clipPath>
          <path d={s.fill} fill={s.r.fill} />
          {s.contours.length > 0 && (
            <g clipPath={`url(#${id}-c${i})`} fill="none" stroke={s.r.contour ?? "rgba(244,235,217,0.35)"} strokeWidth={0.8}>
              {s.contours.map((d, j) => (
                <path key={j} d={d} opacity={1 - j / (s.contours.length + 2)} />
              ))}
            </g>
          )}
        </g>
      ))}
    </g>
  );
}

/** A sun disc whose lower half dissolves into horizontal "atlas" bands. */
function SunDisc({
  cx,
  cy,
  r,
  from = "#d87835",
  to = "#f4ebd9",
  bands = true,
  fade = false,
}: {
  cx: number;
  cy: number;
  r: number;
  from?: string;
  to?: string;
  bands?: boolean;
  fade?: boolean; // dissolve fully into the paper below the horizon line
}) {
  const id = useId().replace(/:/g, "");
  const bandYs = useMemo(() => Array.from({ length: 9 }, (_, i) => cy + r * 0.08 + i * r * 0.1), [cy, r]);
  return (
    <g>
      <defs>
        <linearGradient id={`${id}-sun`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#e07f3a" />
          <stop offset={fade ? "30%" : "38%"} stopColor={from} />
          <stop offset={fade ? "52%" : "72%"} stopColor="#eab27a" stopOpacity={fade ? 0.75 : 0.85} />
          <stop offset={fade ? "74%" : "100%"} stopColor={to} stopOpacity="0" />
        </linearGradient>
        <clipPath id={`${id}-clip`}>
          <circle cx={cx} cy={cy} r={r} />
        </clipPath>
      </defs>
      <circle cx={cx} cy={cy} r={r} fill={`url(#${id}-sun)`} />
      {bands && (
        <g clipPath={`url(#${id}-clip)`} stroke={to} strokeWidth={r * 0.028} opacity={0.75}>
          {bandYs.map((y, i) => (
            <line key={i} x1={cx - r} x2={cx + r} y1={y} y2={y} />
          ))}
        </g>
      )}
    </g>
  );
}

/* ---------------- Cover (login / onboarding) ---------------- */

const COVER_RIDGES: Ridge[] = [
  { base: 455, amp: 70, freqs: [1.1, 3.2, 7.5], phases: [0.6, 1.9, 0.3], valley: 360, fill: "#eaa86f", contour: "rgba(248,241,228,0.55)", contours: 9, gap: 9 },
  { base: 530, amp: 62, freqs: [1.4, 3.7, 8.1], phases: [2.2, 0.4, 1.1], valley: 320, fill: "#d87835", contour: "rgba(248,241,228,0.45)", contours: 8, gap: 9 },
  { base: 600, amp: 54, freqs: [1.2, 4.1, 9.3], phases: [4.1, 2.6, 0.9], valley: 270, fill: "#c65a25", contour: "rgba(248,241,228,0.32)", contours: 7, gap: 9 },
  { base: 665, amp: 48, freqs: [1.6, 3.3, 7.7], phases: [1.3, 5.1, 2.2], valley: 230, fill: "#e8d7b6", contour: "rgba(71,124,112,0.55)", contours: 7, gap: 7 },
  { base: 720, amp: 44, freqs: [1.3, 4.4, 8.6], phases: [3.4, 1.2, 4.4], valley: 190, fill: "#477c70", contour: "rgba(244,235,217,0.3)", contours: 7, gap: 8 },
  { base: 785, amp: 38, freqs: [1.8, 3.9, 9.9], phases: [5.2, 3.3, 1.7], valley: 140, fill: "#1d4037", contour: "rgba(244,235,217,0.22)", contours: 7, gap: 8 },
  { base: 850, amp: 26, freqs: [1.5, 4.8, 10.2], phases: [0.2, 4.4, 2.9], valley: 80, fill: "#142f2a", contour: "rgba(244,235,217,0.16)", contours: 4, gap: 8 },
];

export function CoverLandscape() {
  return (
    <svg className="cover__landscape" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMax slice" aria-hidden="true" focusable="false">
      <MountainLayers width={1440} height={900} ridges={COVER_RIDGES} step={8} />
    </svg>
  );
}

/** The rising sun and orbit arc that sit behind the cover title.
 * Positioned in the content flow (see .cover__sun) so it stays aligned
 * with the title at every viewport height. */
export function CoverSun() {
  // Orbit: circle centred (410, 450), r = 440, drawn from 205deg to 335deg,
  // wide enough that the eyebrow and title sit entirely inside it.
  return (
    <svg className="cover__sun" viewBox="0 0 820 480" aria-hidden="true" focusable="false">
      <path d="M 11 264 A 440 440 0 0 1 809 264" fill="none" stroke="#20231f" strokeOpacity="0.4" strokeWidth="1" />
      <circle cx="410" cy="10" r="5.5" fill="#d87835" />
      <circle cx="116" cy="123" r="4.2" fill="#a8481c" />
      <circle cx="704" cy="123" r="4.2" fill="#a8481c" />
      <SunDisc cx={410} cy={250} r={150} fade />
    </svg>
  );
}

export function CoverOrnament() {
  return (
    <svg width="150" height="14" viewBox="0 0 150 14" aria-hidden="true" focusable="false">
      <g fill="#20231f">
        <circle cx="4" cy="7" r="1.6" />
        <circle cx="30" cy="7" r="1.6" />
        <circle cx="86" cy="7" r="2.4" />
        <circle cx="122" cy="7" r="2.4" />
      </g>
      <path d="M58 7h88" stroke="#20231f" strokeOpacity="0.6" strokeWidth="1" />
    </svg>
  );
}

export function MoonPhases() {
  return (
    <svg width="170" height="26" viewBox="0 0 170 26" aria-hidden="true" focusable="false">
      <g stroke="#e9dcc2" strokeOpacity="0.8" strokeWidth="1.2" fill="none">
        <path d="M10 6v14M160 6v14" />
        <path d="M52 3a10 10 0 0 0 0 20" />
        <path d="M118 3a10 10 0 0 1 0 20" />
      </g>
      <path d="M85 3a10 10 0 0 1 0 20a6 10 0 0 0 0-20z" fill="#e9a462" />
      <circle cx="85" cy="13" r="10" fill="none" stroke="#e9a462" strokeWidth="1" />
    </svg>
  );
}

/* ---------------- Sidebar ---------------- */

const SIDEBAR_RIDGES: Ridge[] = [
  { base: 96, amp: 16, freqs: [1.1, 2.6, 5.3], phases: [0.4, 1.7, 2.6], fill: "#d87835", contour: "rgba(248,241,228,0.35)", contours: 6, gap: 5 },
  { base: 122, amp: 14, freqs: [1.4, 3.1, 6.2], phases: [2.9, 0.7, 1.3], fill: "#c65a25", contour: "rgba(248,241,228,0.28)", contours: 5, gap: 5 },
  { base: 146, amp: 12, freqs: [1.2, 3.6, 7.1], phases: [1.6, 3.8, 0.4], fill: "#477c70", contour: "rgba(244,235,217,0.22)", contours: 5, gap: 5 },
  { base: 172, amp: 10, freqs: [1.7, 2.9, 6.6], phases: [4.4, 2.1, 3.3], fill: "#1d4037", contour: "rgba(244,235,217,0.16)", contours: 4, gap: 5 },
];

export function SidebarLandscape() {
  const id = useId().replace(/:/g, "");
  return (
    <svg className="sidebar__landscape" viewBox="0 0 220 210" preserveAspectRatio="xMidYMax slice" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={`${id}-fade`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#142f2a" stopOpacity="0" />
          <stop offset="100%" stopColor="#142f2a" stopOpacity="0.85" />
        </linearGradient>
      </defs>
      <circle cx="152" cy="84" r="20" fill="#e9b94f" opacity="0.9" />
      <MountainLayers width={220} height={210} ridges={SIDEBAR_RIDGES} step={4} />
      <rect x="0" y="130" width="220" height="80" fill={`url(#${id}-fade)`} />
    </svg>
  );
}

/* ---------------- Small vignettes ---------------- */

const VIGNETTE_RIDGES: Ridge[] = [
  { base: 74, amp: 7, freqs: [1.2, 2.4, 4.1], phases: [0.5, 2.2, 1.0], fill: "#d87835", contour: "rgba(248,241,228,0.4)", contours: 3, gap: 4 },
  { base: 84, amp: 7, freqs: [0.9, 2.8, 5.0], phases: [2.6, 0.8, 3.1], fill: "#477c70", contour: "rgba(244,235,217,0.3)", contours: 4, gap: 4 },
  { base: 96, amp: 5, freqs: [1.4, 3.2, 6.0], phases: [4.0, 1.5, 0.3], fill: "#1d4037", contour: "rgba(244,235,217,0.2)", contours: 3, gap: 4 },
];

/** Sunrise-over-mountains roundel for the primary recommendation. */
export function SunriseVignette({ size = 112 }: { size?: number }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg width={size} height={size} viewBox="0 0 112 112" aria-hidden="true" focusable="false">
      <defs>
        <clipPath id={`${id}-c`}>
          <circle cx="56" cy="56" r="54" />
        </clipPath>
        <linearGradient id={`${id}-sky`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f6e6c4" />
          <stop offset="100%" stopColor="#f0cf98" />
        </linearGradient>
      </defs>
      <g clipPath={`url(#${id}-c)`}>
        <rect width="112" height="112" fill={`url(#${id}-sky)`} />
        <SunDisc cx={56} cy={72} r={28} to="#f6e6c4" />
        <MountainLayers width={112} height={112} ridges={VIGNETTE_RIDGES} step={3} />
      </g>
      <circle cx="56" cy="56" r="54" fill="none" stroke="#d8c9ae" strokeWidth="1.5" />
    </svg>
  );
}

const CLOCK_RIDGES: Ridge[] = [
  { base: 60, amp: 6, freqs: [1.1, 2.3, 4.4], phases: [1.2, 0.3, 2.0], fill: "#2f6458", contour: "rgba(244,235,217,0.28)", contours: 4, gap: 3.5 },
  { base: 70, amp: 5, freqs: [1.5, 2.9, 5.2], phases: [3.1, 1.8, 0.6], fill: "#477c70", contour: "rgba(244,235,217,0.25)", contours: 4, gap: 3.5 },
  { base: 80, amp: 4, freqs: [1.3, 3.4, 6.1], phases: [0.2, 4.0, 2.2], fill: "#1d4037", contour: "rgba(244,235,217,0.18)", contours: 3, gap: 3.5 },
];

/** The astronomical scene inside the 24-hour clock face: night sky,
 * crescent moon, contour mountains and a sun rising at the bottom.
 * Drawn in a 100x100 box and scaled to fit (cx, cy, r). */
export function ClockCenterScene({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  const id = useId().replace(/:/g, "");
  const scale = (r * 2) / 100;
  return (
    <g transform={`translate(${cx - r} ${cy - r}) scale(${scale})`} aria-hidden="true">
      <defs>
        <clipPath id={`${id}-c`}>
          <circle cx="50" cy="50" r="50" />
        </clipPath>
        <radialGradient id={`${id}-sky`} cx="50%" cy="30%" r="70%">
          <stop offset="0%" stopColor="#2c4c43" />
          <stop offset="100%" stopColor="#142f2a" />
        </radialGradient>
        <mask id={`${id}-moon`}>
          <rect width="100" height="100" fill="#fff" />
          <circle cx="54" cy="25" r="7.2" fill="#000" />
        </mask>
      </defs>
      <g clipPath={`url(#${id}-c)`}>
        <rect width="100" height="100" fill={`url(#${id}-sky)`} />
        {[18, 28, 38].map((rr) => (
          <circle key={rr} cx="50" cy="50" r={rr} fill="none" stroke="rgba(244,235,217,0.07)" strokeWidth="0.6" />
        ))}
        <g fill="#efe5d1">
          <circle cx="30" cy="22" r="0.7" />
          <circle cx="68" cy="18" r="0.6" />
          <circle cx="74" cy="34" r="0.5" />
          <circle cx="22" cy="38" r="0.5" />
          <circle cx="62" cy="40" r="0.45" />
        </g>
        <circle cx="50" cy="27" r="8" fill="#efe5d1" mask={`url(#${id}-moon)`} />
        <MountainLayers width={100} height={100} ridges={CLOCK_RIDGES} step={2.5} />
        <SunDisc cx={50} cy={98} r={13} from="#d87835" to="#f4ebd9" bands={false} />
      </g>
    </g>
  );
}
