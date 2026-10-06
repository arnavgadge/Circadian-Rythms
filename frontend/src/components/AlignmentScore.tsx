import type { AlignmentSummary } from "../api/types";

/**
 * The prominent 0-100 alignment score, always shown with its two
 * contributing sub-scores -- never just a giant bare number. The
 * label deliberately reads "alignment with your estimated personal
 * circadian phase," never implying a general health verdict.
 */
export function AlignmentScore({ alignment }: { alignment: AlignmentSummary }) {
  const score = alignment.score;
  return (
    <section className="card" aria-labelledby="alignment-heading">
      <div className="section-label">Alignment</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <h2 id="alignment-heading" style={{ fontSize: 36 }}>
          {score !== null ? Math.round(score) : "—"}
        </h2>
        <span style={{ color: "var(--color-text-faint)" }}>/ 100</span>
      </div>
      <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginTop: 4 }}>
        How closely your recent behavior matches your own estimated circadian phase -- not a general health score.
      </p>

      <dl style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 16 }}>
        <SubScore label="Phase alignment" value={alignment.phase_score} />
        <SubScore label="Behavioral alignment" value={alignment.behavioral_score} />
      </dl>
    </section>
  );
}

function SubScore({ label, value }: { label: string; value: number | null }) {
  return (
    <div>
      <dt style={{ fontSize: 12, color: "var(--color-text-faint)" }}>{label}</dt>
      <dd style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>{value !== null ? Math.round(value) : "—"}</dd>
    </div>
  );
}
