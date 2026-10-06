import type { ContributorSummary } from "../api/types";
import { ContributorCard } from "./ContributorCard";

export function ContributorsList({ contributors }: { contributors: ContributorSummary[] }) {
  return (
    <section className="card" aria-labelledby="contributors-heading">
      <div className="section-label" id="contributors-heading">
        What&apos;s affecting your clock?
      </div>
      {contributors.length === 0 ? (
        <p style={{ color: "var(--color-text-muted)" }}>No contributor data available yet.</p>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 12 }}>
          {contributors.slice(0, 3).map((contributor) => (
            <ContributorCard key={contributor.signal} contributor={contributor} />
          ))}
        </ul>
      )}
      <p style={{ fontSize: 12, color: "var(--color-text-faint)", marginTop: 12 }}>
        Contributors reflect modeled influence within CircadianIQ, not a proven physiological cause.
      </p>
    </section>
  );
}
