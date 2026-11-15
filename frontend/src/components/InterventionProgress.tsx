import { Link } from "react-router-dom";
import type { InterventionHistoryEntry } from "../api/types";
import { CAUSAL_CAVEAT } from "../utils/messages";
import { MEASUREMENT_PHASE_LABELS } from "../utils/terminology";

const MAX_SEGMENTS = 10;

/**
 * Compliance/effect progress for the most recently recommended
 * intervention. Only aggregates what the intervention-history
 * endpoint already returns (a compliant-day count over already-fetched
 * rows, and the latest effect estimate if present) -- it does not
 * compute compliance or an effect estimate itself. The API exposes no
 * planned intervention length, so progress is shown as logged days
 * (one marker per day), never as an invented "Day N of M".
 */
export function InterventionProgress({ entries, historyHref }: { entries: InterventionHistoryEntry[]; historyHref?: string }) {
  if (entries.length === 0) {
    return (
      <section aria-labelledby="intervention-heading">
        <div className="section-label" id="intervention-heading">
          Intervention progress
        </div>
        <div className="empty-state" style={{ paddingTop: 0 }}>
          <p>No intervention history yet.</p>
        </div>
      </section>
    );
  }

  const latestType = entries[0].intervention_type;
  const forType = entries.filter((e) => e.intervention_type === latestType);
  const observed = forType.filter((e) => e.observation_status === "observed");
  const compliant = observed.filter((e) => e.compliance_binary === true);
  const latestWithEffect = forType.find((e) => e.effect_estimate !== null);
  // Oldest -> newest, most recent MAX_SEGMENTS days only.
  const timeline = forType.slice(0, MAX_SEGMENTS).reverse();

  return (
    <section aria-labelledby="intervention-heading">
      <div className="section-label" id="intervention-heading">
        Intervention progress
      </div>
      <p className="serif" style={{ fontSize: 18, fontWeight: 600, textTransform: "capitalize" }}>
        {latestType.replace(/_/g, " ")} intervention
      </p>

      <div className="segments" aria-hidden="true">
        {timeline.map((entry, index) => {
          const filled = entry.compliance_binary === true;
          const missing = entry.observation_status === "missing";
          return (
            <span key={entry.intervention_log_id} style={{ display: "contents" }}>
              {index > 0 && <span className={`segments__link${filled ? " segments__link--filled" : ""}`} />}
              <span
                className={`segments__dot${filled ? " segments__dot--filled" : ""}${missing ? " segments__dot--missing" : ""}`}
                title={`${entry.log_date}: ${missing ? "no data" : filled ? "followed" : "not followed"}`}
              />
            </span>
          );
        })}
      </div>

      <p style={{ fontSize: 14 }}>
        <strong>
          {compliant.length} / {observed.length}
        </strong>{" "}
        <span>days followed</span>
      </p>

      {latestWithEffect && latestWithEffect.effect_estimate !== null && (
        <div style={{ marginTop: 10 }}>
          <p className="small muted">{MEASUREMENT_PHASE_LABELS[latestWithEffect.measurement_phase ?? 1] ?? "Observed change"}</p>
          <p className="serif" style={{ fontSize: 17, fontWeight: 600 }}>
            {Math.abs(Math.round(latestWithEffect.effect_estimate))} min {latestWithEffect.effect_estimate < 0 ? "earlier" : "later"}
          </p>
          <p className="small muted" style={{ marginTop: 4, fontStyle: "italic" }}>
            {CAUSAL_CAVEAT}
          </p>
        </div>
      )}

      {historyHref && (
        <p style={{ marginTop: 12, fontSize: 13 }}>
          <Link to={historyHref}>All intervention records →</Link>
        </p>
      )}
    </section>
  );
}
