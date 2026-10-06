import type { InterventionHistoryEntry } from "../api/types";
import { CAUSAL_CAVEAT } from "../utils/messages";

const PHASE_LABELS: Record<number, string> = {
  1: "Observed change",
  2: "Change compared with a similar previous period",
  3: "Estimated personal effect",
};

/**
 * Compliance/effect progress for the most recently recommended
 * intervention. Only aggregates what the intervention-history
 * endpoint already returns (a compliant-day count over already-fetched
 * rows, and the latest effect estimate if present) -- it does not
 * compute compliance or an effect estimate itself. See
 * docs/ui_architecture.md "Limitations" for what before/after detail
 * isn't yet exposed by the API for this card.
 */
export function InterventionProgress({ entries }: { entries: InterventionHistoryEntry[] }) {
  if (entries.length === 0) {
    return (
      <section className="card" aria-labelledby="intervention-heading">
        <div className="section-label" id="intervention-heading">
          Intervention progress
        </div>
        <p style={{ color: "var(--color-text-muted)" }}>No intervention history yet.</p>
      </section>
    );
  }

  const latestType = entries[0].intervention_type;
  const forType = entries.filter((e) => e.intervention_type === latestType);
  const observed = forType.filter((e) => e.observation_status === "observed");
  const compliant = observed.filter((e) => e.compliance_binary === true);
  const latestWithEffect = forType.find((e) => e.effect_estimate !== null);

  return (
    <section className="card" aria-labelledby="intervention-heading">
      <div className="section-label" id="intervention-heading">
        {latestType.replace(/_/g, " ")} intervention
      </div>
      <p style={{ fontSize: 15 }}>
        <strong>
          {compliant.length} / {observed.length}
        </strong>{" "}
        days followed
      </p>

      {latestWithEffect && latestWithEffect.effect_estimate !== null && (
        <div style={{ marginTop: 12 }}>
          <p style={{ fontSize: 13, color: "var(--color-text-faint)" }}>
            {PHASE_LABELS[latestWithEffect.measurement_phase ?? 1] ?? "Observed change"}
          </p>
          <p style={{ fontSize: 15 }}>
            {Math.abs(Math.round(latestWithEffect.effect_estimate))} min {latestWithEffect.effect_estimate < 0 ? "earlier" : "later"}
          </p>
          <p style={{ fontSize: 12, color: "var(--color-text-faint)", marginTop: 6 }}>{CAUSAL_CAVEAT}</p>
        </div>
      )}
    </section>
  );
}
