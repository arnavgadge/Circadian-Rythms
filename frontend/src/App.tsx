import { useState } from "react";
import { Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { Dashboard } from "./pages/Dashboard";
import { DailyEntry } from "./pages/DailyEntry";
import { History } from "./pages/History";
import { Interventions } from "./pages/Interventions";
import { OnboardingPage } from "./pages/Onboarding";
import { ParticipantPicker } from "./pages/ParticipantPicker";
import { ResearchDemo, ResearchDemoEntry } from "./pages/ResearchDemo";

/** Reads and validates the :participantId route param; an invalid ID
 * returns to the participant entry screen. */
function useParticipantId(): number | null {
  const { participantId } = useParams();
  const id = Number(participantId);
  return Number.isInteger(id) && id > 0 ? id : null;
}

function DashboardRoute({ devMode }: { devMode: boolean }) {
  const id = useParticipantId();
  if (id === null) return <Navigate to="/" replace />;
  return <Dashboard key={id} participantId={id} devMode={devMode} />;
}

function DailyEntryRoute() {
  const id = useParticipantId();
  if (id === null) return <Navigate to="/" replace />;
  return <DailyEntry key={id} participantId={id} />;
}

function HistoryRoute({ devMode }: { devMode: boolean }) {
  const id = useParticipantId();
  if (id === null) return <Navigate to="/" replace />;
  return <History key={id} participantId={id} devMode={devMode} />;
}

function InterventionsRoute() {
  const id = useParticipantId();
  if (id === null) return <Navigate to="/" replace />;
  return <Interventions key={id} participantId={id} />;
}

function ResearchDemoRoute() {
  const id = useParticipantId();
  if (id === null) return <Navigate to="/demo" replace />;
  return <ResearchDemo key={id} participantId={id} />;
}

function OnboardingRoute() {
  const navigate = useNavigate();
  return <OnboardingPage onComplete={(id) => navigate(`/log/${id}`)} />;
}

export default function App() {
  const [devMode, setDevMode] = useState(false);
  const toggleDevMode = () => setDevMode((v) => !v);

  return (
    <Routes>
      <Route path="/" element={<ParticipantPicker />} />
      <Route path="/onboarding" element={<OnboardingRoute />} />
      <Route element={<AppShell devMode={devMode} onToggleDevMode={toggleDevMode} />}>
        <Route path="/dashboard/:participantId" element={<DashboardRoute devMode={devMode} />} />
        <Route path="/log/:participantId" element={<DailyEntryRoute />} />
        <Route path="/history/:participantId" element={<HistoryRoute devMode={devMode} />} />
        <Route path="/interventions/:participantId" element={<InterventionsRoute />} />
        <Route path="/demo" element={<ResearchDemoEntry />} />
        <Route path="/demo/:participantId" element={<ResearchDemoRoute />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
