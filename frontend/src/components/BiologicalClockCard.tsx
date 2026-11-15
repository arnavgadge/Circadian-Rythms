import type { BehaviorEntry, StatusResponse } from "../api/types";
import { ClockVisualization, type ClockMarker } from "./ClockVisualization";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { formatDuration, to12Hour } from "../utils/time";
import { QUALIFIER_TEXT } from "../utils/messages";

/**
 * The primary dashboard card: "Where is my biological clock?" Uses
 * "Estimated Biological Clock," never "Clinical DLMO," and always
 * shows the compact boundary note directly on the card (never hidden
 * behind a tooltip). Shows no fabricated value when the API says a
 * prediction is unavailable.
 *
 * `observation` (optional) is the day's logged behavior from the
 * behavior-history endpoint, shown as a colour-keyed signal legend --
 * values are displayed exactly as logged, never derived.
 */
export function BiologicalClockCard({ status, observation }: { status: StatusResponse; observation?: BehaviorEntry | null }) {
  if (!status.prediction_available) {
    return (
      <section className="clock-card" aria-labelledby="clock-heading">
        <div className="clock-card__summary">
          <div className="section-label">Estimated Biological Clock</div>
          <h2 id="clock-heading" className="serif" style={{ fontSize: 30, lineHeight: 1.15 }}>
            Not enough data for today&apos;s estimate
          </h2>
          <p className="muted">{status.qualifier_message ?? "Not enough reliable data was available for today's estimate."}</p>
          <p className="boundary-note" style={{ marginTop: 6 }}>
            {status.boundary_note}
          </p>
        </div>
        <ClockVisualization
          markers={[
            { key: "dlmo", label: "Estimated biological clock", value: null, shape: "diamond", colorVar: "--rust" },
          ]}
        />
      </section>
    );
  }

  const markers: ClockMarker[] = [
    { key: "dlmo", label: "Estimated biological clock", value: status.biological_clock, shape: "diamond", colorVar: "--rust" },
    { key: "ideal", label: "Ideal sleep onset", value: status.alignment.ideal_sleep_onset, shape: "circle", colorVar: "--teal" },
    { key: "actual", label: "Actual recent sleep onset", value: status.alignment.actual_sleep_onset, shape: "square", colorVar: "--burnt" },
  ];

  const qualifier = status.qualifier_message ?? (status.confidence.label ? QUALIFIER_TEXT[status.confidence.label] : undefined);

  return (
    <section className="clock-card" aria-labelledby="clock-heading">
      <div className="clock-card__summary">
        <div>
          <div className="section-label" style={{ marginBottom: 2 }}>
            Estimated Biological Clock
          </div>
          <div className="small muted">(DLMO, model-based)</div>
        </div>
        <h2 id="clock-heading" className="display-time">
          {status.approximate ? "~" : ""}
          {to12Hour(status.biological_clock)}
        </h2>
        {status.chronotype && (
          <p className="clock-card__chronotype">
            Chronotype <span aria-hidden="true">/</span> <span className="badge badge--sage">{status.chronotype}</span>
          </p>
        )}
        <div>
          <ConfidenceBadge confidence={status.confidence} />
        </div>
        {qualifier && <p className="small muted">{qualifier}</p>}
        <p className="boundary-note">{status.boundary_note}</p>
      </div>

      <ClockVisualization
        markers={markers}
        arc={{ fromKey: "actual", toKey: "ideal", colorVar: "--burnt", label: "Gap between recent and ideal sleep onset" }}
      >
        <SignalLegend observation={observation} />
      </ClockVisualization>
    </section>
  );
}

function SignalLegend({ observation }: { observation?: BehaviorEntry | null }) {
  if (observation === undefined) return null;
  if (observation === null) {
    return <p className="legend--signals small muted">No behavior logged for this date.</p>;
  }
  const rows: Array<{ key: string; label: string; colorVar: string; value: string }> = [
    { key: "sleep", label: "Sleep onset", colorVar: "--sig-sleep", value: observation.sleep_onset ? to12Hour(observation.sleep_onset) : "—" },
    { key: "light", label: "Morning light", colorVar: "--sig-light", value: formatDuration(observation.morning_light_duration_minutes) },
    { key: "screen", label: "Evening screens", colorVar: "--sig-screen", value: formatDuration(observation.evening_screen_duration_minutes) },
    { key: "meal", label: "Last meal", colorVar: "--sig-meal", value: observation.last_meal_time ? to12Hour(observation.last_meal_time) : "—" },
  ];
  return (
    <ul className="legend legend--signals" aria-label="Logged behavior for this date">
      {rows.map((row) => (
        <li key={row.key}>
          <span className="signal-swatch" style={{ background: `var(${row.colorVar})` }} aria-hidden="true" />
          <span>{row.label}</span>
          <strong>{row.value}</strong>
        </li>
      ))}
    </ul>
  );
}
