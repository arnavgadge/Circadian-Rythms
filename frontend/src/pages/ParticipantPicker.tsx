import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

/**
 * Landing screen: load an existing participant by ID, or start
 * onboarding. No demo values are hard-coded here -- entering any
 * participant ID that already exists in the database (created via
 * onboarding, a backend diagnostic script, or the synthetic dataset)
 * loads real data through the API. See docs/ui_architecture.md
 * "Demo participant".
 */
export function ParticipantPicker() {
  const [participantId, setParticipantId] = useState("");
  const navigate = useNavigate();

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const id = Number(participantId);
    if (Number.isFinite(id) && id > 0) {
      navigate(`/dashboard/${id}`);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 420, margin: "80px auto 0", textAlign: "center" }}>
      <h1 style={{ fontSize: 24 }}>CircadianIQ</h1>
      <p style={{ color: "var(--color-text-muted)", marginTop: 8 }}>
        Estimated from behavioral patterns. Not a clinical measurement.
      </p>

      <form onSubmit={handleSubmit} style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 12 }}>
        <label htmlFor="participant-id" style={{ fontSize: 13, color: "var(--color-text-muted)", textAlign: "left" }}>
          Participant ID
        </label>
        <input
          id="participant-id"
          inputMode="numeric"
          value={participantId}
          onChange={(e) => setParticipantId(e.target.value)}
          placeholder="e.g. 1"
          style={{ padding: "10px 12px", borderRadius: "var(--radius-sm)", border: "1px solid var(--color-border)" }}
        />
        <button type="submit" className="button button--primary" disabled={!participantId}>
          View dashboard
        </button>
      </form>

      <p style={{ marginTop: 24, fontSize: 13 }}>
        New here? <Link to="/onboarding">Create a participant profile</Link>
      </p>
    </div>
  );
}
