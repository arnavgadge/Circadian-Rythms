import { useCallback, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAction, useFetch } from "../hooks/useApi";
import { AlignmentBreakdown } from "../components/AlignmentBreakdown";
import { AlignmentScore } from "../components/AlignmentScore";
import { BiologicalClockCard } from "../components/BiologicalClockCard";
import { ContributorsList } from "../components/ContributorsList";
import { DevPanel } from "../components/DevPanel";
import { ErrorState, InlineNotice } from "../components/ErrorState";
import { InterventionProgress } from "../components/InterventionProgress";
import { LoadingState, SkeletonLines } from "../components/LoadingState";
import { FocusEmpty, RecommendationCard } from "../components/RecommendationCard";
import { RhythmTimeline } from "../components/RhythmTimeline";
import { SafetyBanner } from "../components/SafetyBanner";
import { Icon } from "../components/atlas/Icon";
import { DateNavigator } from "../components/layout/DateNavigator";
import { PageHeader } from "../components/layout/PageHeader";
import { INFERENCE_LOADING_TEXT } from "../utils/messages";
import { todayIso } from "../utils/time";

/**
 * The Personal Time Atlas dashboard. Every value shown comes from an
 * existing read endpoint:
 *
 * - `GET /status` (optionally `?target_date=` when a date is chosen in
 *   the header; otherwise the most recent result) -- clock, alignment,
 *   contributors, confidence, safety
 * - `GET /recommendation/current` -- primary focus + supporting nudges
 * - `GET /interventions` -- intervention progress
 * - `GET /behavior?start_date=&end_date=` for the shown date -- the
 *   daily rhythm timeline (requested only once /status says which
 *   date is being shown)
 * - `GET /circadian/history?limit=1` -- only while Research Mode is on
 *
 * Inference is never triggered by rendering: only the explicit
 * "Update today's estimate" button calls `POST /inference`.
 */
export function Dashboard({ participantId, devMode = false }: { participantId: number; devMode?: boolean }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedDate = searchParams.get("date");

  const setSelectedDate = useCallback(
    (next: string | null) => {
      const params = new URLSearchParams(searchParams);
      if (next) params.set("date", next);
      else params.delete("date");
      setSearchParams(params, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const statusState = useFetch(() => api.getStatus(participantId, selectedDate ?? undefined), [participantId, selectedDate, refreshKey]);
  const recommendationState = useFetch(() => api.getCurrentRecommendation(participantId), [participantId, refreshKey]);
  const interventionState = useFetch(() => api.getInterventionHistory(participantId, { limit: 60 }), [participantId, refreshKey]);

  const shownDate = statusState.data?.target_date ?? selectedDate;
  const observationState = useFetch(
    () => api.getBehaviorHistory(participantId, { start_date: shownDate ?? undefined, end_date: shownDate ?? undefined, limit: 1 }),
    [participantId, shownDate, refreshKey],
    Boolean(shownDate),
  );
  const historyState = useFetch(
    () => api.getCircadianHistory(participantId, { end_date: shownDate ?? undefined, limit: 1 }),
    [participantId, shownDate, refreshKey],
    devMode,
  );

  const inferenceAction = useAction(() => api.runInference(participantId, {}));

  const handleRunInference = useCallback(async () => {
    try {
      await inferenceAction.run();
    } catch {
      return; // inferenceAction.error is rendered below; keep the current view.
    }
    // Inference computes today's result: show the latest estimate.
    if (selectedDate) setSelectedDate(null);
    setRefreshKey((k) => k + 1);
  }, [inferenceAction, selectedDate, setSelectedDate]);

  const status = statusState.data;
  const observation = observationState.data ? (observationState.data.entries.find((e) => e.date === shownDate) ?? null) : observationState.error ? undefined : null;

  const header = (
    <PageHeader
      title="Your biological time map"
      subtitle="A model-based view of your internal clock and daily rhythm."
      actions={
        <>
          <DateNavigator id="dashboard-date" label="Dashboard date" value={shownDate ?? todayIso()} onChange={(d) => setSelectedDate(d)} />
          {selectedDate && (
            <button type="button" className="button button--quiet button--small" onClick={() => setSelectedDate(null)}>
              Latest
            </button>
          )}
          <button type="button" className="button button--primary button--small" onClick={handleRunInference} disabled={inferenceAction.loading}>
            <Icon name="refresh" size={15} />
            {inferenceAction.loading ? INFERENCE_LOADING_TEXT : "Update today's estimate"}
          </button>
        </>
      }
    />
  );

  if (statusState.loading && !status) {
    return (
      <div>
        {header}
        <LoadingState label="Loading your circadian profile…" />
      </div>
    );
  }
  if (statusState.error || !status) {
    return (
      <div>
        {header}
        <ErrorState error={statusState.error} onRetry={statusState.refetch} />
      </div>
    );
  }

  const recommendationMissing = recommendationState.error instanceof ApiError && recommendationState.error.status === 404;
  const viewingPastDate = Boolean(selectedDate && status.target_date && selectedDate !== todayIso());

  return (
    <div className="dashboard">
      {header}

      {inferenceAction.error && <ErrorState error={inferenceAction.error} />}

      <BiologicalClockCard status={status} observation={observation} />

      {status.safety.active && recommendationState.data && <SafetyBanner safety={status.safety} recommendation={recommendationState.data} />}

      <div className="ruled-row ruled-row--2">
        <div>
          <AlignmentScore alignment={status.alignment} />
          <AlignmentBreakdown components={status.alignment.components} />
        </div>
        <ContributorsList contributors={status.contributors} />
      </div>

      <div className="atlas-section">
        {observationState.loading ? (
          <SkeletonLines lines={4} />
        ) : observationState.error ? (
          <InlineNotice error={observationState.error} label="This day's logged behavior couldn't be loaded." onRetry={observationState.refetch} />
        ) : (
          <RhythmTimeline date={shownDate} entry={observation ?? null} />
        )}
        {!observationState.loading && !observationState.error && !observation && (
          <p style={{ marginTop: -4, fontSize: 13 }}>
            <Link to={`/log/${participantId}${shownDate ? `?date=${shownDate}` : ""}`}>Log behavior for this date →</Link>
          </p>
        )}
      </div>

      <div className="ruled-row ruled-row--focus">
        <div>
          {recommendationState.loading && !recommendationState.data ? (
            <SkeletonLines lines={4} />
          ) : recommendationState.data?.suppressed ? (
            <section aria-labelledby="paused-heading">
              <div className="section-label" id="paused-heading">
                Recommendations paused
              </div>
              <p className="small muted">Personalized suggestions are paused while this pattern continues — see the safety note above.</p>
            </section>
          ) : recommendationState.data ? (
            <RecommendationCard
              recommendation={recommendationState.data}
              note={viewingPastDate ? "This is your current recommendation, not the one for the date shown above." : undefined}
            />
          ) : recommendationMissing ? (
            <FocusEmpty />
          ) : (
            <InlineNotice error={recommendationState.error} label="Your recommendation couldn't be loaded." onRetry={recommendationState.refetch} />
          )}
        </div>
        <div>
          {interventionState.loading && !interventionState.data ? (
            <SkeletonLines lines={3} />
          ) : interventionState.data ? (
            <InterventionProgress entries={interventionState.data.entries} historyHref={`/interventions/${participantId}`} />
          ) : (
            <InlineNotice error={interventionState.error} label="Intervention progress couldn't be loaded." onRetry={interventionState.refetch} />
          )}
        </div>
      </div>

      {devMode && (
        <DevPanel status={status} latestHistoryEntry={historyState.data?.entries.find((e) => e.date === status.target_date) ?? historyState.data?.entries[0]} />
      )}
    </div>
  );
}
