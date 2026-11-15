import type { StatusResponse } from "../api/types";
import { contributorLabel } from "../utils/terminology";
import { Icon } from "./atlas/Icon";
import { iconForSignal } from "./atlas/signals";

const SIGNALS = ["evening_screen", "morning_light", "meal_timing", "social_jetlag", "exercise"];
const RANK_SHADE: Record<number, string> = { 1: "var(--evergreen)", 2: "var(--teal)", 3: "#9fbcb3" };

/**
 * How each day's persisted top-3 contributor ranking evolves across the
 * prediction days. Every cell is that day's stored rank (from
 * GET /status?target_date=) -- blank where the signal was not ranked,
 * never assumed to carry over from another day.
 */
export function ContributorEvolution({
  days,
  selectedDay,
  onSelect,
}: {
  days: Array<{ day: number; date: string; status?: StatusResponse }>;
  selectedDay: number;
  onSelect: (day: number) => void;
}) {
  if (days.length === 0) return <p className="small muted">No persisted contributor rankings for this period.</p>;
  const columns = `repeat(${days.length}, minmax(0, 1fr))`;

  return (
    <div className="evolution" role="table" aria-label="Contributor rank by prediction day">
      <div className="evolution__row" role="row">
        <span className="evolution__label" role="columnheader">
          <span className="visually-hidden">Signal</span>
        </span>
        <div className="evolution__cells" style={{ gridTemplateColumns: columns }}>
          {days.map((d) => (
            <button
              key={d.day}
              type="button"
              role="columnheader"
              className={`evolution__day${d.day === selectedDay ? " is-selected" : ""}`}
              onClick={() => onSelect(d.day)}
              aria-label={`Select day ${d.day}`}
            >
              {d.day}
            </button>
          ))}
        </div>
      </div>
      {SIGNALS.map((signal) => (
        <div className="evolution__row" role="row" key={signal}>
          <span className="evolution__label" role="rowheader">
            <Icon name={iconForSignal(signal)} size={15} />
            {contributorLabel(signal)}
          </span>
          <div className="evolution__cells" style={{ gridTemplateColumns: columns }}>
            {days.map((d) => {
              const rank = d.status?.contributors.find((c) => c.signal === signal)?.rank ?? null;
              const loaded = Boolean(d.status);
              return (
                <span
                  key={d.day}
                  role="cell"
                  className={`evolution__cell${d.day === selectedDay ? " is-selected" : ""}`}
                  style={rank ? { background: RANK_SHADE[rank] ?? "var(--sand)", color: rank === 3 ? "var(--forest)" : "var(--on-dark)" } : undefined}
                  title={`Day ${d.day} (${d.date}): ${!loaded ? "loading" : rank ? `ranked #${rank}` : "not in top 3"}`}
                  aria-label={`${contributorLabel(signal)}, day ${d.day}: ${!loaded ? "loading" : rank ? `rank ${rank}` : "not ranked"}`}
                >
                  {rank ?? ""}
                </span>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
