import type { PrimaryRecommendation } from "../api/types";

/** A single supporting nudge -- deliberately lower visual weight than
 * the primary recommendation card. At most two are ever rendered by
 * the parent (see RecommendationSection). */
export function NudgeCard({ nudge }: { nudge: PrimaryRecommendation }) {
  return (
    <li className="card" style={{ padding: "var(--space-3) var(--space-4)", background: "var(--color-surface-muted)", border: "none" }}>
      <p style={{ fontSize: 14 }}>{nudge.text}</p>
    </li>
  );
}
