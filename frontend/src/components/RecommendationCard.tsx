import type { RecommendationResponse } from "../api/types";
import { NudgeCard } from "./NudgeCard";
import { SunriseVignette } from "./atlas/Illustrations";
import { expectedImprovementSourceLabel, personalizationLabel } from "../utils/terminology";
import { formatTargetDisplay } from "../utils/time";

/**
 * The dominant primary-recommendation section, plus up to two lower-
 * priority supporting nudges -- never three equal-weight
 * recommendations. When the API reports the recommendation as
 * suppressed (a Phase 14 safety decision), nothing is rendered at all
 * -- the safety banner (see SafetyBanner) owns that message instead;
 * this component never overrides that decision.
 */
export function RecommendationCard({ recommendation, note }: { recommendation: RecommendationResponse; note?: string }) {
  if (recommendation.suppressed) {
    return null;
  }

  if (!recommendation.available || !recommendation.primary) {
    return <FocusEmpty />;
  }

  const { primary } = recommendation;
  const sourceLabel = expectedImprovementSourceLabel(primary.expected_improvement_source) ?? personalizationLabel(recommendation.personalization_phase);
  const supporting = recommendation.supporting.slice(0, 2);

  return (
    <div className="ruled-row ruled-row--nested">
      <section aria-labelledby="recommendation-heading">
        <div className="section-label" id="recommendation-heading">
          This week&apos;s primary focus
        </div>
        <div className="focus">
          <SunriseVignette />
          <div>
            <h3 className="focus__title">{primary.text}</h3>
            {primary.target_display && (
              <p style={{ fontSize: 13.5 }}>
                Today&apos;s target: <strong>{formatTargetDisplay(primary.target_display)}</strong>
              </p>
            )}
            <hr className="focus__divider" />
            {primary.expected_improvement_minutes !== null && (
              <p style={{ fontSize: 13 }}>
                Expected improvement: <strong>~{Math.abs(Math.round(primary.expected_improvement_minutes))} min</strong>
                {sourceLabel && <span className="muted"> · {sourceLabel}</span>}
              </p>
            )}
            <p className="small muted" style={{ marginTop: 6 }}>
              A gradual shift based on your recent pattern.
            </p>
            {note && (
              <p className="small muted" style={{ marginTop: 6, fontStyle: "italic" }}>
                {note}
              </p>
            )}
          </div>
        </div>
      </section>

      <section aria-labelledby="nudges-heading">
        <div className="section-label" id="nudges-heading">
          Supporting nudges
        </div>
        {supporting.length > 0 ? (
          <ul className="nudge-list">
            {supporting.map((nudge, index) => (
              <NudgeCard key={`${nudge.intervention_type}-${index}`} nudge={nudge} />
            ))}
          </ul>
        ) : (
          <p className="small muted">No supporting nudges alongside this week&apos;s focus.</p>
        )}
      </section>
    </div>
  );
}

/** Shown when no recommendation exists yet (none computed, or none
 * available for this participant). Never fabricates a suggestion. */
export function FocusEmpty() {
  return (
    <section aria-labelledby="recommendation-heading">
      <div className="section-label" id="recommendation-heading">
        This week&apos;s primary focus
      </div>
      <div className="focus">
        <SunriseVignette />
        <div className="empty-state" style={{ paddingTop: 0 }}>
          <span className="empty-state__title">No focus set yet</span>
          <p>No recommendation is available yet. One appears after a daily estimate has been computed.</p>
        </div>
      </div>
    </section>
  );
}
