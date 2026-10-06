import { Link } from "react-router-dom";

export function Header({ participantId, devMode, onToggleDevMode }: { participantId: number | null; devMode: boolean; onToggleDevMode: () => void }) {
  return (
    <header style={{ borderBottom: "1px solid var(--color-border)", padding: "14px 24px", display: "flex", alignItems: "center", gap: 20 }}>
      <Link to="/" style={{ fontWeight: 700, color: "var(--color-text)", textDecoration: "none" }}>
        CircadianIQ
      </Link>
      {participantId !== null && (
        <nav aria-label="Main" style={{ display: "flex", gap: 16, fontSize: 14 }}>
          <Link to={`/dashboard/${participantId}`}>Dashboard</Link>
          <Link to={`/log/${participantId}`}>Log behavior</Link>
        </nav>
      )}
      <label style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--color-text-faint)" }}>
        <input type="checkbox" checked={devMode} onChange={onToggleDevMode} />
        Research mode
      </label>
    </header>
  );
}
