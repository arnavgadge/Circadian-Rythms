import { useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { Header } from "./components/Header";
import { Dashboard } from "./pages/Dashboard";
import { DailyEntry } from "./pages/DailyEntry";
import { Onboarding } from "./pages/Onboarding";
import { ParticipantPicker } from "./pages/ParticipantPicker";

function DashboardRoute({ devMode }: { devMode: boolean }) {
  const { participantId } = useParams();
  const id = Number(participantId);
  if (!Number.isFinite(id)) return <Navigate to="/" replace />;
  return <Dashboard participantId={id} devMode={devMode} />;
}

function DailyEntryRoute() {
  const { participantId } = useParams();
  const id = Number(participantId);
  if (!Number.isFinite(id)) return <Navigate to="/" replace />;
  return <DailyEntry participantId={id} />;
}

function OnboardingRoute() {
  const navigate = useNavigate();
  return <Onboarding onComplete={(id) => navigate(`/log/${id}`)} />;
}

export default function App() {
  const [devMode, setDevMode] = useState(false);
  const location = useLocation();
  const match = /\/(?:dashboard|log)\/(\d+)/.exec(location.pathname);
  const headerParticipantId = match ? Number(match[1]) : null;

  return (
    <div>
      <Header participantId={headerParticipantId} devMode={devMode} onToggleDevMode={() => setDevMode((v) => !v)} />
      <main style={{ maxWidth: 1100, margin: "0 auto", padding: "24px" }}>
        <Routes>
          <Route path="/" element={<ParticipantPicker />} />
          <Route path="/onboarding" element={<OnboardingRoute />} />
          <Route path="/dashboard/:participantId" element={<DashboardRoute devMode={devMode} />} />
          <Route path="/log/:participantId" element={<DailyEntryRoute />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
