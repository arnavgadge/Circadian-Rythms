import type { CircadianHistoryEntry, StatusResponse } from "../api/types";

/**
 * Research/debug panel -- clearly separated from the consumer view and
 * off by default. Only surfaces fields the API already returns (no
 * internal jargon is invented); several values the brief mentions
 * (raw XGBoost vs. state estimates, model/pipeline version) are not
 * currently exposed by any Phase 15 endpoint and are therefore omitted
 * rather than fabricated -- see docs/ui_architecture.md "Limitations".
 */
export function DevPanel({ status, latestHistoryEntry }: { status: StatusResponse; latestHistoryEntry?: CircadianHistoryEntry }) {
  return (
    <section className="card" style={{ gridColumn: "1 / -1", background: "var(--color-surface-muted)", fontFamily: "var(--font-family-mono)", fontSize: 12 }}>
      <div className="badge badge--neutral" style={{ marginBottom: 10 }}>
        Research / debug
      </div>
      <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 10 }}>
        <Row label="confidence_score" value={status.confidence.score} />
        <Row label="confidence_label" value={status.confidence.label} />
        <Row label="disagreement_regime" value={latestHistoryEntry?.disagreement_regime ?? null} />
        <Row label="prediction_status" value={latestHistoryEntry?.prediction_status ?? null} />
        <Row label="target_date" value={status.target_date} />
        <Row label="personalization_phase" value={status.recommendation.expected_improvement_source} />
      </dl>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <dt style={{ color: "var(--color-text-faint)" }}>{label}</dt>
      <dd style={{ margin: 0 }}>{value ?? "null"}</dd>
    </div>
  );
}
