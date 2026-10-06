import type { AlignmentComponents } from "../api/types";
import { ALIGNMENT_COMPONENT_LABELS } from "../utils/terminology";

const ORDER: Array<keyof AlignmentComponents> = ["sleep_consistency", "morning_light", "evening_screen", "meal_timing", "social_jetlag"];

/** The five behavioral-alignment components as compact progress bars.
 * Score only -- no invented explanatory text; a screen-reader label
 * always states the numeric score, never color alone. */
export function AlignmentBreakdown({ components }: { components: AlignmentComponents | null }) {
  if (!components) return null;

  return (
    <section className="card" aria-labelledby="breakdown-heading">
      <div className="section-label" id="breakdown-heading">
        Alignment breakdown
      </div>
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 14 }}>
        {ORDER.map((key) => {
          const value = components[key];
          return (
            <li key={key}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                <span>{ALIGNMENT_COMPONENT_LABELS[key]}</span>
                <span style={{ color: "var(--color-text-muted)" }}>{value !== null ? Math.round(value) : "No data"}</span>
              </div>
              <div
                role="progressbar"
                aria-label={`${ALIGNMENT_COMPONENT_LABELS[key]}: ${value !== null ? `${Math.round(value)} out of 100` : "no data"}`}
                aria-valuenow={value !== null ? Math.round(value) : undefined}
                aria-valuemin={0}
                aria-valuemax={100}
                style={{ height: 8, borderRadius: 999, background: "var(--color-surface-muted)", overflow: "hidden" }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${value !== null ? Math.max(2, Math.min(100, value)) : 0}%`,
                    background: "var(--color-accent)",
                    borderRadius: 999,
                  }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
