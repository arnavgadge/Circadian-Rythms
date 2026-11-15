import type { ReactNode } from "react";
import type { CircadianHistoryEntry, StatusResponse } from "../api/types";

/**
 * Research mode panel -- clearly separated from the consumer view and
 * off by default. Only surfaces fields the API already returns (no
 * internal jargon is invented); several values the brief mentions
 * (raw XGBoost vs. state estimates, model/pipeline version, feature
 * completeness) are not currently exposed by any Phase 15 endpoint and
 * are therefore listed as unavailable rather than fabricated -- see
 * docs/ui_architecture.md "Limitations".
 */
export function DevPanel({ status, latestHistoryEntry }: { status: StatusResponse; latestHistoryEntry?: CircadianHistoryEntry }) {
  const components = status.alignment.components;
  return (
    <section className="research-panel" aria-labelledby="research-heading">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <div>
          <div className="section-label" id="research-heading" style={{ marginBottom: 2 }}>
            Research mode
          </div>
          <p className="small muted">Raw API fields for this participant and date. Values are shown exactly as returned.</p>
        </div>
        <span className="badge badge--neutral">Research / debug</span>
      </div>

      <div className="research-grid">
        <Group title="Observation context">
          <Row label="participant_id" value={status.participant_id} />
          <Row label="target_date" value={status.target_date} />
          <Row label="prediction_status" value={latestHistoryEntry?.prediction_status ?? null} />
          <Row label="disagreement_regime" value={latestHistoryEntry?.disagreement_regime ?? null} />
        </Group>
        <Group title="Model-estimated phase">
          <Row label="prediction_available" value={String(status.prediction_available)} />
          <Row label="biological_clock" value={status.biological_clock} />
          <Row label="approximate" value={String(status.approximate)} />
          <Row label="ideal_sleep_onset" value={status.alignment.ideal_sleep_onset} />
          <Row label="actual_sleep_onset" value={status.alignment.actual_sleep_onset} />
          <Row label="chronotype" value={status.chronotype} />
        </Group>
        <Group title="Model confidence">
          <Row label="confidence_score" value={status.confidence.score} />
          <Row label="confidence_label" value={status.confidence.label} />
          <Row label="confidence.approximate" value={String(status.confidence.approximate)} />
          <Row label="qualifier_message" value={status.qualifier_message} />
        </Group>
        <Group title="Alignment outputs">
          <Row label="score" value={status.alignment.score} />
          <Row label="phase_score" value={status.alignment.phase_score} />
          <Row label="behavioral_score" value={status.alignment.behavioral_score} />
          {components &&
            (Object.keys(components) as Array<keyof typeof components>).map((key) => <Row key={key} label={key} value={components[key]} />)}
        </Group>
        <Group title="Contributors (raw)">
          {status.contributors.length === 0 ? (
            <Row label="contributors" value="[]" />
          ) : (
            status.contributors.map((c) => (
              <Row
                key={c.signal}
                label={`#${c.rank} ${c.signal}`}
                value={`score=${c.contributor_score ?? "null"} effect=${c.effect_minutes ?? "null"} deficit=${c.alignment_deficit ?? "null"} dir=${c.direction ?? "null"}`}
              />
            ))
          )}
        </Group>
        <Group title="Recommendation & safety">
          <Row label="personalization_phase" value={status.recommendation.expected_improvement_source} />
          <Row label="intervention_type" value={status.recommendation.intervention_type} />
          <Row label="recommendation_suppressed" value={String(status.safety.recommendation_suppressed)} />
          <Row label="highest_severity" value={status.safety.highest_severity} />
          <Row label="flag_types" value={status.safety.flag_types.join(", ") || "[]"} />
        </Group>
        <Group title="Not exposed by the API">
          <Row label="xgb_estimate" value="unavailable" />
          <Row label="state_estimate" value="unavailable" />
          <Row label="feature_completeness" value="unavailable" />
          <Row label="model_version" value="unavailable" />
        </Group>
      </div>
    </section>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="research-group">
      <h3>{title}</h3>
      <dl>{children}</dl>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value ?? "null"}</dd>
    </>
  );
}
