import { useCallback, useState } from "react";
import { api } from "../api/client";
import { useAction, useFetch } from "../hooks/useApi";
import { AlignmentBreakdown } from "../components/AlignmentBreakdown";
import { AlignmentScore } from "../components/AlignmentScore";
import { BiologicalClockCard } from "../components/BiologicalClockCard";
import { ContributorsList } from "../components/ContributorsList";
import { DevPanel } from "../components/DevPanel";
import { ErrorState } from "../components/ErrorState";
import { InterventionProgress } from "../components/InterventionProgress";
import { LoadingState } from "../components/LoadingState";
import { RecommendationCard } from "../components/RecommendationCard";
import { SafetyBanner } from "../components/SafetyBanner";
import { TrajectoryChart } from "../components/TrajectoryChart";
import { INFERENCE_LOADING_TEXT } from "../utils/messages";

export function Dashboard({ participantId, devMode = false }: { participantId: number; devMode?: boolean }) {
  const [refreshKey, setRefreshKey] = useState(0);

  const statusState = useFetch(() => api.getStatus(participantId), [participantId, refreshKey]);
  const recommendationState = useFetch(() => api.getCurrentRecommendation(participantId), [participantId, refreshKey]);
  const historyState = useFetch(() => api.getCircadianHistory(participantId, { limit: 90 }), [participantId, refreshKey]);
  const interventionState = useFetch(() => api.getInterventionHistory(participantId, { limit: 60 }), [participantId, refreshKey]);

  const inferenceAction = useAction(() => api.runInference(participantId, {}));

  const refreshAll = useCallback(() => setRefreshKey((k) => k + 1), []);

  const handleRunInference = useCallback(async () => {
    await inferenceAction.run();
    refreshAll();
  }, [inferenceAction, refreshAll]);

  if (statusState.loading && !statusState.data) {
    return <LoadingState label="Loading your circadian profile…" />;
  }
  if (statusState.error) {
    return <ErrorState error={statusState.error} onRetry={statusState.refetch} />;
  }
  const status = statusState.data;
  if (!status) return null;

  return (
    <div className="dashboard-grid">
      <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "flex-end" }}>
        <button type="button" className="button button--primary" onClick={handleRunInference} disabled={inferenceAction.loading}>
          {inferenceAction.loading ? INFERENCE_LOADING_TEXT : "Update today's estimate"}
        </button>
      </div>

      {inferenceAction.error && (
        <div style={{ gridColumn: "1 / -1" }}>
          <ErrorState error={inferenceAction.error} />
        </div>
      )}

      <div style={{ gridColumn: "1 / -1" }}>
        <BiologicalClockCard status={status} />
      </div>

      {status.safety.active && recommendationState.data && (
        <div style={{ gridColumn: "1 / -1" }}>
          <SafetyBanner safety={status.safety} recommendation={recommendationState.data} />
        </div>
      )}

      <AlignmentScore alignment={status.alignment} />
      <AlignmentBreakdown components={status.alignment.components} />

      {recommendationState.data && (
        <div style={{ gridColumn: "1 / -1" }}>
          <RecommendationCard recommendation={recommendationState.data} />
        </div>
      )}

      <ContributorsList contributors={status.contributors} />

      {interventionState.data && <InterventionProgress entries={interventionState.data.entries} />}

      <div style={{ gridColumn: "1 / -1" }}>
        {historyState.data && <TrajectoryChart entries={historyState.data.entries} />}
      </div>

      {devMode && <DevPanel status={status} latestHistoryEntry={historyState.data?.entries[0]} />}
    </div>
  );
}
