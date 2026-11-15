import type { ReactNode } from "react";

/**
 * Thin-line icon set shared across the whole UI. One semantic icon per
 * concept (bed = sleep, sun = light, monitor = screens, cutlery = meals,
 * cup = caffeine) so the same category always looks the same.
 * Purely decorative: always aria-hidden; meaning is carried by text.
 */
export type IconName =
  | "dashboard"
  | "pencil"
  | "history"
  | "interventions"
  | "research"
  | "bed"
  | "sun"
  | "monitor"
  | "cutlery"
  | "cup"
  | "activity"
  | "calendar"
  | "clock"
  | "arrow-right"
  | "chevron-left"
  | "chevron-right"
  | "user"
  | "trend-up"
  | "plus"
  | "minus"
  | "menu"
  | "refresh"
  | "moon"
  | "switch"
  | "check"
  | "info"
  | "jetlag";

const PATHS: Record<IconName, ReactNode> = {
  dashboard: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  pencil: (
    <>
      <path d="M4 20h4L19.5 8.5a2.1 2.1 0 0 0-3-3L5 17v3z" />
      <path d="M14.5 7.5l3 3" />
    </>
  ),
  history: (
    <>
      <path d="M4 20h16" />
      <path d="M7 17v-6M11 17V6M15 17v-8M19 17v-4" />
    </>
  ),
  interventions: (
    <>
      <ellipse cx="12" cy="6" rx="7.5" ry="2.6" />
      <path d="M4.5 6v5.5c0 1.4 3.4 2.6 7.5 2.6s7.5-1.2 7.5-2.6V6" />
      <path d="M4.5 11.5V17c0 1.4 3.4 2.6 7.5 2.6s7.5-1.2 7.5-2.6v-5.5" />
    </>
  ),
  research: (
    <>
      <path d="M9 3.5h6M10 3.5v6L4.6 18.8a1.5 1.5 0 0 0 1.3 2.2h12.2a1.5 1.5 0 0 0 1.3-2.2L14 9.5v-6" />
      <path d="M7.3 15h9.4" />
    </>
  ),
  bed: (
    <>
      <path d="M3 6v13M3 15h18v4M21 15v-3a3 3 0 0 0-3-3h-8v6" />
      <circle cx="6.5" cy="11.5" r="1.8" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" />
    </>
  ),
  monitor: (
    <>
      <rect x="3" y="4.5" width="18" height="12" rx="1" />
      <path d="M8.5 20h7M12 16.5V20" />
    </>
  ),
  cutlery: (
    <>
      <path d="M7 3v18M4.5 3v5a2.5 2.5 0 0 0 5 0V3" />
      <path d="M17 21V3c-2 0-3.5 2.5-3.5 6s1.5 4 3.5 4" />
    </>
  ),
  cup: (
    <>
      <path d="M4 9h12v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V9z" />
      <path d="M16 11h1.5a2.5 2.5 0 0 1 0 5H16" />
      <path d="M8 3.5c0 1.4 1 1.6 1 3M12 3.5c0 1.4 1 1.6 1 3" />
    </>
  ),
  activity: <path d="M3 12h4l2.5-6.5 4.5 13 2.5-6.5H21" />,
  calendar: (
    <>
      <rect x="3.5" y="5" width="17" height="15.5" rx="1.5" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  "arrow-right": <path d="M5 12h14M13 6l6 6-6 6" />,
  "chevron-left": <path d="M14.5 6l-6 6 6 6" />,
  "chevron-right": <path d="M9.5 6l6 6-6 6" />,
  user: (
    <>
      <circle cx="12" cy="8" r="3.8" />
      <path d="M4.5 20.5c1.4-3.8 4.2-5.6 7.5-5.6s6.1 1.8 7.5 5.6" />
    </>
  ),
  "trend-up": <path d="M7 17L17 7M9.5 7H17v7.5" />,
  plus: <path d="M12 5.5v13M5.5 12h13" />,
  minus: <path d="M5.5 12h13" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  refresh: (
    <>
      <path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" />
      <path d="M19.5 4.5v4h-4" />
    </>
  ),
  moon: <path d="M19.5 14.5A8 8 0 0 1 9.5 4.5a8 8 0 1 0 10 10z" />,
  switch: <path d="M15 4h4.5v16H15M10.5 8l-4 4 4 4M6.5 12H16" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5.5M12 7.8v.4" />
    </>
  ),
  jetlag: (
    <>
      <circle cx="9" cy="12" r="6" />
      <path d="M9 8.5V12l2 1.5" />
      <path d="M16.5 7.5a6 6 0 0 1 0 9" />
    </>
  ),
};

export function Icon({ name, size = 18, strokeWidth = 1.5, className }: { name: IconName; size?: number; strokeWidth?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {PATHS[name]}
    </svg>
  );
}
