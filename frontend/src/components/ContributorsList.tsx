import type { ContributorSummary } from "../api/types";
import { ContributorCard } from "./ContributorCard";

export function ContributorsList({ contributors }: { contributors: ContributorSummary[] }) {
  return (
    <section aria-labelledby="contributors-heading">
      <div className="section-label" id="contributors-heading">
        Top contributors
      </div>
      {contributors.length === 0 ? (
        <div className="empty-state">
          <span className="empty-state__title">Nothing ranked yet</span>
          <p>No contributor data available yet. Contributors appear once a daily estimate has been computed from your logged behavior.</p>
        </div>
      ) : (
        <ol className="contributor-list">
          {contributors.slice(0, 3).map((contributor) => (
            <ContributorCard key={contributor.signal} contributor={contributor} />
          ))}
        </ol>
      )}
      <p className="small muted" style={{ marginTop: 12, fontStyle: "italic" }}>
        Contributors reflect modeled influence within CircadianIQ, not a proven physiological cause.
      </p>
    </section>
  );
}
