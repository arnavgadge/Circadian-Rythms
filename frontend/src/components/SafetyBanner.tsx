import type { RecommendationResponse, SafetySummary } from "../api/types";
import { HIGH_SEVERITY_BODY, HIGH_SEVERITY_HEADLINE, NON_DIAGNOSTIC_STATEMENT } from "../utils/messages";
import { flagTypeLabel } from "../utils/terminology";
import { Icon } from "./atlas/Icon";

/**
 * Renders nothing when there is no active safety flag. A MODERATE
 * flag shows a calm "Pattern note" alongside the still-available
 * recommendation. A HIGH flag replaces the normal recommendation
 * entirely with a prominent safety message -- **the severity always
 * comes from the API**; this component never determines it itself.
 */
export function SafetyBanner({ safety, recommendation }: { safety: SafetySummary; recommendation: RecommendationResponse }) {
  if (!safety.active || !safety.highest_severity) {
    return null;
  }

  if (safety.highest_severity === "HIGH") {
    return (
      <section className="notice notice--alert" role="alert" aria-labelledby="safety-heading">
        <span style={{ color: "var(--rust)", display: "inline-flex", paddingTop: 4 }}>
          <Icon name="info" size={22} />
        </span>
        <div>
          <div className="badge badge--low" style={{ marginBottom: 8 }}>
            Safety note
          </div>
          <h3 id="safety-heading" className="notice__title">
            {recommendation.safety_message ?? HIGH_SEVERITY_HEADLINE}
          </h3>
          <p style={{ marginTop: 6 }}>{HIGH_SEVERITY_BODY}</p>
          <p className="muted" style={{ marginTop: 4 }}>
            {recommendation.non_diagnostic_statement ?? NON_DIAGNOSTIC_STATEMENT}
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="notice notice--moderate" aria-labelledby="pattern-note-heading">
      <span style={{ color: "var(--burnt)", display: "inline-flex", paddingTop: 4 }}>
        <Icon name="info" size={20} />
      </span>
      <div>
        <div className="badge badge--moderate" style={{ marginBottom: 8 }}>
          Pattern note
        </div>
        <h3 id="pattern-note-heading" className="notice__title" style={{ fontSize: 17 }}>
          {safety.flag_types.map(flagTypeLabel).join(" · ") || "An unusual pattern was noted."}
        </h3>
        <p className="muted" style={{ marginTop: 4 }}>
          {NON_DIAGNOSTIC_STATEMENT}
        </p>
      </div>
    </section>
  );
}
