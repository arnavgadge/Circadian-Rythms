import type { RecommendationResponse } from "../api/types";
import { NudgeCard } from "./NudgeCard";
import { expectedImprovementSourceLabel, personalizationLabel } from "../utils/terminology";

/**
 * The dominant primary-recommendation card, plus up to two lower-
 * priority supporting nudges -- never three equal-weight
 * recommendations. When the API reports the recommendation as
 * suppressed (a Phase 14 safety decision), the normal card is not
 * rendered at all -- the safety banner (see SafetyBanner) owns that
 * message instead; this component never overrides that decision.
 */
export function RecommendationCard({ recommendation }: { recommendation: RecommendationResponse }) {
  if (recommendation.suppressed) {
    return null;
  }

  if (!recommendation.available || !recommendation.primary) {
    return (
      <section className="card" aria-labelledby="recommendation-heading">
        <div className="section-label" id="recommendation-heading">
          This week&apos;s primary focus
        </div>
        <p style={{ color: "var(--color-text-muted)" }}>No recommendation is available yet.</p>
      </section>
    );
  }

  const { primary } = recommendation;
  const sourceLabel = expectedImprovementSourceLabel(primary.expected_improvement_source) ?? personalizationLabel(recommendation.personalization_phase);

  return (
    <section className="card" aria-labelledby="recommendation-heading" style={{ borderColor: "var(--color-accent)", borderWidth: 2 }}>
      <div className="section-label" id="recommendation-heading">
        This week&apos;s primary focus
      </div>
      <h3 style={{ fontSize: 22, marginBottom: 8 }}>{primary.text}</h3>

      {primary.target_display && (
        <p style={{ fontSize: 14, color: "var(--color-text-muted)" }}>
          Today&apos;s target: <strong>{primary.target_display}</strong>
        </p>
      )}

      {primary.expected_improvement_minutes !== null && (
        <p style={{ fontSize: 14, marginTop: 6 }}>
          Expected improvement: <strong>~{Math.abs(Math.round(primary.expected_improvement_minutes))} min</strong>
          {sourceLabel && <span style={{ color: "var(--color-text-faint)" }}> · {sourceLabel}</span>}
        </p>
      )}

      {recommendation.supporting.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <div className="section-label">Supporting nudges</div>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
            {recommendation.supporting.slice(0, 2).map((nudge, index) => (
              <NudgeCard key={`${nudge.intervention_type}-${index}`} nudge={nudge} />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
