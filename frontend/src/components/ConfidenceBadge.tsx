import type { ConfidenceSummary } from "../api/types";
import { confidenceLabel } from "../utils/terminology";

const TONE_BY_LABEL: Record<string, "good" | "moderate" | "low" | "neutral"> = {
  high: "good",
  moderate: "moderate",
  low: "low",
  no_prediction: "neutral",
};

/** Shows confidence without making it frightening: a label + score,
 * never just a bare number, and never color alone (the label text is
 * always present). */
export function ConfidenceBadge({ confidence }: { confidence: ConfidenceSummary }) {
  const tone = TONE_BY_LABEL[confidence.label ?? "no_prediction"] ?? "neutral";
  const label = confidenceLabel(confidence.label);

  return (
    <span className={`badge badge--${tone}`} role="status" aria-label={`Confidence: ${label}${confidence.score !== null ? `, ${Math.round(confidence.score)} out of 100` : ""}`}>
      {label}
      {confidence.score !== null && (
        <span aria-hidden="true"> · {confidence.approximate ? "~" : ""}{Math.round(confidence.score)}/100</span>
      )}
    </span>
  );
}
