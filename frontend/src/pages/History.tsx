import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useFetch } from "../hooks/useApi";
import { BehaviorHeatmap } from "../components/BehaviorHeatmap";
import { ErrorState, InlineNotice } from "../components/ErrorState";
import { LoadingState, SkeletonLines } from "../components/LoadingState";
import { TrajectoryChart } from "../components/TrajectoryChart";
import { PageHeader } from "../components/layout/PageHeader";
import { formatDateLong, to12Hour } from "../utils/time";
import { predictionStatusLabel } from "../utils/terminology";

const RANGES = [7, 30, 90] as const;
type Range = (typeof RANGES)[number];

/**
 * Rhythm History: how the estimated clock and logged behavior changed
 * over time. Choosing a range re-requests both existing history
 * endpoints with `limit=<range>` (the API returns the most recent N
 * records, newest first) -- nothing is filtered from a fixed array.
 */
export function History({ participantId, devMode = false }: { participantId: number; devMode?: boolean }) {
  const [range, setRange] = useState<Range>(30);

  const circadian = useFetch(() => api.getCircadianHistory(participantId, { limit: range }), [participantId, range]);
  const behavior = useFetch(() => api.getBehaviorHistory(participantId, { limit: range }), [participantId, range]);

  return (
    <div>
      <PageHeader
        title="Rhythm history"
        subtitle="How your estimated clock and daily behaviors have changed over time."
        actions={
          <div className="segmented" role="group" aria-label="Time range">
            {RANGES.map((days) => (
              <button key={days} type="button" aria-pressed={range === days} onClick={() => setRange(days)}>
                {days} days
              </button>
            ))}
          </div>
        }
      />

      {circadian.loading && !circadian.data ? (
        <LoadingState label="Loading your rhythm history…" />
      ) : circadian.error ? (
        <ErrorState error={circadian.error} onRetry={circadian.refetch} />
      ) : circadian.data && circadian.data.entries.length === 0 ? (
        <div className="empty-state" style={{ paddingTop: 0 }}>
          <span className="empty-state__title">Your history is still being written</span>
          <p>No daily estimates exist yet. Log a few days of behavior and update your estimate to start this record.</p>
          <Link to={`/log/${participantId}`} className="button button--primary button--small" style={{ marginTop: 8 }}>
            Log behavior
          </Link>
        </div>
      ) : (
        <div aria-busy={circadian.loading || undefined} style={{ opacity: circadian.loading ? 0.6 : 1, transition: "opacity 160ms ease" }}>
          <TrajectoryChart entries={circadian.data?.entries ?? []} />
          {circadian.data && (
            <p className="small muted" style={{ marginTop: 6 }}>
              {circadian.data.count} daily {circadian.data.count === 1 ? "estimate" : "estimates"} in view
              {circadian.data.entries.length > 0 &&
                ` · ${formatDateLong(circadian.data.entries[circadian.data.entries.length - 1].date)} – ${formatDateLong(circadian.data.entries[0].date)}`}
              . Hover a point for its value.
            </p>
          )}
        </div>
      )}

      <section className="atlas-section" style={{ marginTop: 28 }} aria-labelledby="patterns-heading">
        <div className="section-label" id="patterns-heading">
          Behavioral patterns ({range} days)
        </div>
        {behavior.loading && !behavior.data ? (
          <SkeletonLines lines={5} />
        ) : behavior.error ? (
          <InlineNotice error={behavior.error} label="Logged behavior couldn't be loaded." onRetry={behavior.refetch} />
        ) : (
          <>
            <BehaviorHeatmap entries={behavior.data?.entries ?? []} />
            {behavior.data && behavior.data.entries.length === 0 && (
              <p style={{ fontSize: 13 }}>
                <Link to={`/log/${participantId}`}>Log today&apos;s behavior →</Link>
              </p>
            )}
          </>
        )}
      </section>

      {devMode && circadian.data && circadian.data.entries.length > 0 && (
        <section className="research-panel" style={{ marginTop: 28 }} aria-labelledby="history-raw-heading">
          <div className="section-label" id="history-raw-heading">
            Research mode · raw history records
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="record-table" style={{ fontFamily: "var(--font-family-mono)", fontSize: 11.5 }}>
              <thead>
                <tr>
                  <th>date</th>
                  <th>biological_clock</th>
                  <th>confidence</th>
                  <th>alignment</th>
                  <th>disagreement_regime</th>
                  <th>prediction_status</th>
                </tr>
              </thead>
              <tbody>
                {circadian.data.entries.map((e) => (
                  <tr key={e.date}>
                    <td data-label="date">{e.date}</td>
                    <td data-label="clock">{e.biological_clock ? `${e.biological_clock} (${to12Hour(e.biological_clock)})` : "null"}</td>
                    <td data-label="confidence">
                      {e.confidence_score ?? "null"} {e.confidence_label ? `· ${e.confidence_label}` : ""}
                    </td>
                    <td data-label="alignment">{e.alignment_score ?? "null"}</td>
                    <td data-label="regime">{e.disagreement_regime ?? "null"}</td>
                    <td data-label="status">
                      {e.prediction_status} <span className="muted">({predictionStatusLabel(e.prediction_status)})</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
