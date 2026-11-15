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
    <section aria-labelledby="alignment-heading">
      <div className="section-label">Alignment</div>
      <div style={{ display: "grid", gridTemplateColumns: "auto minmax(0, 1fr)", gap: 28, alignItems: "center" }}>
        <div className="score">
          <h2 id="alignment-heading" className="score__value">
            {score !== null ? Math.round(score) : "—"}
          </h2>
          <span className="score__max">/ 100</span>
        </div>
        <dl style={{ margin: 0, display: "flex", flexDirection: "column", gap: 14 }}>
          <SubScore label="Phase alignment" value={alignment.phase_score} colorVar="--teal" />
          <SubScore label="Behavioral alignment" value={alignment.behavioral_score} colorVar="--gold" />
        </dl>
      </div>
      <p className="small muted" style={{ marginTop: 14 }}>
        How closely your recent behavior matches your own estimated circadian phase — not a general health score.
      </p>
    </section>
  );
}

function SubScore({ label, value, colorVar }: { label: string; value: number | null; colorVar: string }) {
  const rounded = value !== null ? Math.round(value) : null;
  return (
    <div>
      <div className="meter-row">
        <dt>{label}</dt>
        <dd style={{ margin: 0 }} className="meter-row__value">
          <span>{rounded !== null ? rounded : "—"}</span>
          <span>/ 100</span>
        </dd>
      </div>
      <div
        className="meter"
        role="progressbar"
        aria-label={`${label}: ${rounded !== null ? `${rounded} out of 100` : "no data"}`}
        aria-valuenow={rounded ?? undefined}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="meter__fill" style={{ width: `${rounded !== null ? Math.max(2, Math.min(100, rounded)) : 0}%`, background: `var(${colorVar})` }} />
      </div>
    </div>
  );
}
