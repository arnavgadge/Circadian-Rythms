import type { ContributorSummary } from "../api/types";
import { contributorLabel, directionLabel } from "../utils/terminology";

/**
 * One ranked contributor. Uses "contributor" / "estimated effect" /
 * "modeled influence" language only -- never "cause." Today's anomaly
 * (if any) is shown as a visually separate note beneath the habit-level
 * contributor, never merged into the same line (see docs/ui_architecture.md
 * "Dashboard structure").
 */
export function ContributorCard({ contributor }: { contributor: ContributorSummary }) {
  return (
    <li className="card" style={{ padding: "var(--space-4)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{ fontWeight: 600 }}>
          {contributor.rank}. {contributorLabel(contributor.signal)}
        </span>
        {contributor.contributor_score !== null && (
          <span style={{ fontSize: 12, color: "var(--color-text-faint)" }}>score {Math.round(contributor.contributor_score)}</span>
        )}
      </div>

      <dl style={{ margin: "8px 0 0", fontSize: 13, color: "var(--color-text-muted)", display: "flex", flexDirection: "column", gap: 2 }}>
        {contributor.effect_minutes !== null && (
          <div>
            Estimated phase effect: <strong>{Math.abs(Math.round(contributor.effect_minutes))} min</strong>
          </div>
        )}
        {contributor.alignment_deficit !== null && (
          <div>
            Alignment deficit: <strong>{Math.round(contributor.alignment_deficit)}</strong>
          </div>
        )}
        {contributor.direction && <div>{directionLabel(contributor.direction)}</div>}
      </dl>

      {contributor.today_anomaly && (
        <div
          className="badge badge--moderate"
          style={{ marginTop: 10, display: "inline-flex" }}
          role="note"
          aria-label={`Today's pattern for ${contributorLabel(contributor.signal)} was unusual compared to your recent habit.`}
        >
          Today&apos;s pattern was unusual
        </div>
      )}
    </li>
  );
}
