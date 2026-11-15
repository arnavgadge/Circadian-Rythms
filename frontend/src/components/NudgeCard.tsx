import type { PrimaryRecommendation } from "../api/types";
import { Icon } from "./atlas/Icon";
import { iconForSignal } from "./atlas/signals";

/** A single supporting nudge -- deliberately lower visual weight than
 * the primary recommendation. At most two are ever rendered by the
 * parent (see RecommendationCard). Text is the API's own template text. */
export function NudgeCard({ nudge }: { nudge: PrimaryRecommendation }) {
  return (
    <li className="nudge">
      <span style={{ color: "var(--burnt)", display: "inline-flex", paddingTop: 1 }}>
        <Icon name={iconForSignal(nudge.intervention_type)} size={22} strokeWidth={1.4} />
      </span>
      <p>{nudge.text}</p>
    </li>
  );
}
