import type { RecommendationResponse, SafetySummary } from "../api/types";
import { HIGH_SEVERITY_BODY, HIGH_SEVERITY_HEADLINE, NON_DIAGNOSTIC_STATEMENT } from "../utils/messages";
import { flagTypeLabel } from "../utils/terminology";

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
      <section className="card" role="alert" aria-labelledby="safety-heading" style={{ borderColor: "var(--color-low)", background: "var(--color-low-soft)" }}>
        <div className="badge badge--low" style={{ marginBottom: 10 }}>
          Safety note
        </div>
        <h3 id="safety-heading" style={{ fontSize: 18 }}>
          {recommendation.safety_message ?? HIGH_SEVERITY_HEADLINE}
        </h3>
        <p style={{ marginTop: 8, fontSize: 14 }}>{HIGH_SEVERITY_BODY}</p>
        <p style={{ marginTop: 8, fontSize: 13, color: "var(--color-text-muted)" }}>
          {recommendation.non_diagnostic_statement ?? NON_DIAGNOSTIC_STATEMENT}
        </p>
      </section>
    );
  }

  return (
    <section className="card" aria-labelledby="pattern-note-heading" style={{ background: "var(--color-moderate-soft)", borderColor: "transparent" }}>
      <div className="badge badge--moderate" style={{ marginBottom: 10 }}>
        Pattern note
      </div>
      <h3 id="pattern-note-heading" style={{ fontSize: 16 }}>
        {safety.flag_types.map(flagTypeLabel).join(" · ") || "An unusual pattern was noted."}
      </h3>
      <p style={{ marginTop: 8, fontSize: 13, color: "var(--color-text-muted)" }}>{NON_DIAGNOSTIC_STATEMENT}</p>
    </section>
  );
}
