import type { AlignmentComponents } from "../api/types";
import { ALIGNMENT_COMPONENT_LABELS } from "../utils/terminology";
import { Icon } from "./atlas/Icon";
import { iconForSignal } from "./atlas/signals";

const ORDER: Array<keyof AlignmentComponents> = ["sleep_consistency", "morning_light", "evening_screen", "meal_timing", "social_jetlag"];

/** The same colour per signal everywhere (see theme.css "Signal semantics"). */
const COLOR_BY_COMPONENT: Record<keyof AlignmentComponents, string> = {
  sleep_consistency: "--sig-sleep",
  morning_light: "--sig-light",
  evening_screen: "--sig-screen",
  meal_timing: "--sig-meal",
  social_jetlag: "--sig-jetlag",
};

/** The five behavioral-alignment components as compact progress bars.
 * Score only -- no invented explanatory text; a screen-reader label
 * always states the numeric score, never color alone. */
export function AlignmentBreakdown({ components }: { components: AlignmentComponents | null }) {
  if (!components) return null;

  return (
    <section aria-labelledby="breakdown-heading" style={{ marginTop: 22 }}>
      <div className="section-label section-label--muted" id="breakdown-heading">
        Behavioral components
      </div>
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 9 }}>
        {ORDER.map((key) => {
          const value = components[key];
          return (
            <li key={key} style={{ display: "grid", gridTemplateColumns: "18px 138px minmax(0, 1fr) 34px", alignItems: "center", gap: 10, fontSize: 12.5 }}>
              <Icon name={iconForSignal(key)} size={15} />
              <span>{ALIGNMENT_COMPONENT_LABELS[key]}</span>
              <div
                className="meter"
                style={{ height: 4 }}
                role="progressbar"
                aria-label={`${ALIGNMENT_COMPONENT_LABELS[key]}: ${value !== null ? `${Math.round(value)} out of 100` : "no data"}`}
                aria-valuenow={value !== null ? Math.round(value) : undefined}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div
                  className="meter__fill"
                  style={{ width: `${value !== null ? Math.max(2, Math.min(100, value)) : 0}%`, background: `var(${COLOR_BY_COMPONENT[key]})` }}
                />
              </div>
              <span className="muted" style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                {value !== null ? Math.round(value) : "No data"}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
