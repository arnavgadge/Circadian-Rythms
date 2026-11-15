import { Outlet, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { useFetch } from "../../hooks/useApi";
import { useParticipant } from "../../hooks/useParticipant";
import { SYNTHETIC_LABEL, isDemoParticipantCode } from "../../config/demo";
import { Sidebar } from "./Sidebar";

/**
 * Shared layout for every participant page: the evergreen sidebar plus
 * the parchment content area. Mounted once as a layout route, so the
 * sidebar (and its single health/version request) persists across
 * page navigation instead of being re-created per page.
 */
export function AppShell({ devMode, onToggleDevMode }: { devMode: boolean; onToggleDevMode: () => void }) {
  const { participantId } = useParams();
  const id = Number(participantId);
  const validId = Number.isInteger(id) && id > 0 ? id : null;
  const health = useFetch(() => api.getHealth(), []);
  // The participant record (code) is looked up once per id and cached,
  // so a synthetic demonstration participant is always labelled as such.
  const { participant } = useParticipant(validId);
  const synthetic = isDemoParticipantCode(participant?.participant_code);
  const versionLabel = health.data?.api_version ? `v${health.data.api_version.replace(/^v/, "")}` : null;

  return (
    <div className="shell">
      <Sidebar
        participantId={validId}
        participantCode={participant?.participant_code ?? null}
        synthetic={synthetic}
        devMode={devMode}
        onToggleDevMode={onToggleDevMode}
        versionLabel={versionLabel}
      />
      <main className="main">
        <div className="main__inner">
          {synthetic && (
            <p className="synthetic-banner" role="note">
              <strong>{SYNTHETIC_LABEL}</strong> · {participant?.participant_code} · every value shown is a real CircadianIQ pipeline output computed
              from synthetic input data, not a real person.
            </p>
          )}
          <Outlet />
        </div>
      </main>
    </div>
  );
}
