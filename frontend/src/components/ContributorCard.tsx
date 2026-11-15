import type { ContributorSummary } from "../api/types";
import { contributorLabel, directionLabel, directionShortLabel } from "../utils/terminology";
import { Icon, type IconName } from "./atlas/Icon";

const DIRECTION_STYLE: Record<string, { icon: IconName; badge: string; color: string }> = {
  hurting: { icon: "trend-up", badge: "badge--low", color: "var(--rust)" },
  opportunity_missed: { icon: "plus", badge: "badge--moderate", color: "var(--burnt)" },
  neutral: { icon: "minus", badge: "badge--neutral", color: "var(--brown)" },
};

/**
 * One ranked contributor. Uses "contributor" / "estimated effect" /
 * "modeled influence" language only -- never "cause." Today's anomaly
 * (if any) is shown as a visually separate note beneath the habit-level
 * contributor, never merged into the same line (see docs/ui_architecture.md
 * "Dashboard structure").
 */
export function ContributorCard({ contributor }: { contributor: ContributorSummary }) {
  const style = DIRECTION_STYLE[contributor.direction ?? ""] ?? DIRECTION_STYLE.neutral;
  const shortLabel = directionShortLabel(contributor.direction);

  const meta: string[] = [];
  if (contributor.effect_minutes !== null) meta.push(`Estimated phase effect ${Math.abs(Math.round(contributor.effect_minutes))} min`);
  if (contributor.alignment_deficit !== null) meta.push(`alignment deficit ${Math.round(contributor.alignment_deficit)}`);
  if (contributor.contributor_score !== null) meta.push(`score ${Math.round(contributor.contributor_score)}`);

  return (
    <li className="contributor">
      <span className="rank-marker" aria-label={`Rank ${contributor.rank}`}>
        {String(contributor.rank).padStart(2, "0")}
      </span>
      <span className="contributor__name">{contributorLabel(contributor.signal)}</span>
      {shortLabel ? (
        <span className="contributor__direction" title={directionLabel(contributor.direction) ?? undefined}>
          <span style={{ color: style.color, display: "inline-flex" }}>
            <Icon name={style.icon} size={15} strokeWidth={1.8} />
          </span>
          <span className={`badge ${style.badge}`}>{shortLabel}</span>
        </span>
      ) : (
        <span />
      )}
      {meta.length > 0 && <span className="contributor__meta">{meta.join(" · ")}</span>}

      {contributor.today_anomaly && (
        <div
          className="anomaly-note"
          role="note"
          aria-label={`Today's pattern for ${contributorLabel(contributor.signal)} was unusual compared to your recent habit.`}
        >
          Today&apos;s pattern was unusual
        </div>
      )}
    </li>
  );
}
