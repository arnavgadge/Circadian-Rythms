import type { StatusResponse } from "../api/types";
import { ClockVisualization, type ClockMarker } from "./ClockVisualization";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { to12Hour } from "../utils/time";
import { QUALIFIER_TEXT } from "../utils/messages";

/**
 * The primary dashboard card: "Where is my biological clock?" Uses
 * "Estimated Biological Clock," never "Clinical DLMO," and always
 * shows the compact boundary note directly on the card (never hidden
 * behind a tooltip). Shows no fabricated value when the API says a
 * prediction is unavailable.
 */
export function BiologicalClockCard({ status }: { status: StatusResponse }) {
  if (!status.prediction_available) {
    return (
      <section className="card" aria-labelledby="clock-heading">
        <div className="section-label">Estimated Biological Clock</div>
        <h2 id="clock-heading" style={{ fontSize: 22, marginBottom: 8 }}>
          Not enough data for today&apos;s estimate
        </h2>
        <p style={{ color: "var(--color-text-muted)" }}>
          {status.qualifier_message ?? "Not enough reliable data was available for today's estimate."}
        </p>
        <p className="boundary-note" style={{ marginTop: 16 }}>
          {status.boundary_note}
        </p>
      </section>
    );
  }

  const markers: ClockMarker[] = [
    { key: "dlmo", label: "Estimated biological clock", value: status.biological_clock, shape: "diamond", colorVar: "--color-accent" },
    { key: "ideal", label: "Ideal sleep onset", value: status.alignment.ideal_sleep_onset, shape: "circle", colorVar: "--color-good" },
    { key: "actual", label: "Actual recent sleep onset", value: status.alignment.actual_sleep_onset, shape: "square", colorVar: "--color-moderate" },
  ];

  return (
    <section className="card" aria-labelledby="clock-heading">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
        <div>
          <div className="section-label">Estimated Biological Clock</div>
          <h2 id="clock-heading" style={{ fontSize: 40, fontVariantNumeric: "tabular-nums" }}>
            {status.approximate ? "~" : ""}
            {to12Hour(status.biological_clock)}
          </h2>
          {status.chronotype && (
            <p style={{ color: "var(--color-text-muted)", marginTop: 4 }}>
              Chronotype: <strong>{status.chronotype}</strong>
            </p>
          )}
          <div style={{ marginTop: 10 }}>
            <ConfidenceBadge confidence={status.confidence} />
          </div>
          {status.qualifier_message && (
            <p style={{ marginTop: 10, fontSize: 13, color: "var(--color-text-muted)" }}>{status.qualifier_message}</p>
          )}
          {!status.qualifier_message && status.confidence.label && QUALIFIER_TEXT[status.confidence.label] && (
            <p style={{ marginTop: 10, fontSize: 13, color: "var(--color-text-muted)" }}>{QUALIFIER_TEXT[status.confidence.label]}</p>
          )}
        </div>
        <ClockVisualization markers={markers} />
      </div>
      <p className="boundary-note" style={{ marginTop: 20 }}>
        {status.boundary_note}
      </p>
    </section>
  );
}
