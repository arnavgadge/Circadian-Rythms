import { useId } from "react";

/**
 * The CircadianIQ mark: a burnt-orange crescent with a small rising sun
 * on its inner edge -- part moon, part sunrise. Decorative only; the
 * brand name next to it carries the meaning.
 */
export function BrandMark({ size = 36, tone = "light" }: { size?: number; tone?: "light" | "dark" }) {
  const id = useId().replace(/:/g, "");
  const crescent = tone === "dark" ? "#d87835" : "#c96e2e";
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id={`${id}-g`} cx="35%" cy="35%" r="75%">
          <stop offset="0%" stopColor="#e9b94f" />
          <stop offset="60%" stopColor={crescent} />
          <stop offset="100%" stopColor="#a8481c" />
        </radialGradient>
        <mask id={`${id}-m`}>
          <rect width="40" height="40" fill="#fff" />
          <circle cx="26" cy="16.5" r="12" fill="#000" />
        </mask>
      </defs>
      <circle cx="19" cy="20" r="15" fill={`url(#${id}-g)`} mask={`url(#${id}-m)`} />
      <circle cx="29.5" cy="9" r="1.6" fill="#e9b94f" />
    </svg>
  );
}

export function BrandLockup({ tone = "light", tagline = true }: { tone?: "light" | "dark"; tagline?: boolean }) {
  return (
    <>
      <BrandMark tone={tone} size={40} />
      <span>
        <span className="brand-name">CircadianIQ</span>
        {tagline && <span className="brand-tagline">Circadian cartography</span>}
      </span>
    </>
  );
}
