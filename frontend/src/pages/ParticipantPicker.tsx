import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { BrandLockup } from "../components/atlas/BrandMark";
import { Icon } from "../components/atlas/Icon";
import { CoverLandscape, CoverOrnament, CoverSun, MoonPhases } from "../components/atlas/Illustrations";
import { friendlyErrorMessage } from "../utils/errors";

/**
 * Landing screen -- the "cover" of the atlas. Loads an existing
 * participant by ID, or starts onboarding. The ID is checked against
 * the existing `GET /participants/{id}` endpoint before navigating, so
 * an unknown ID shows an inline message instead of an empty dashboard.
 * No demo values are hard-coded here (see docs/ui_architecture.md
 * "Demo participant").
 */
export function ParticipantPicker() {
  const [participantId, setParticipantId] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = participantId.trim();
    const id = Number(trimmed);
    if (!trimmed || !Number.isInteger(id) || id <= 0) {
      setError("Enter a numeric participant ID, for example 1.");
      return;
    }
    setError(null);
    setChecking(true);
    try {
      await api.getParticipant(id);
      navigate(`/dashboard/${id}`);
    } catch (err) {
      setChecking(false);
      if (err instanceof ApiError && err.status === 404) {
        setError(`No participant with ID ${id} was found. Check the ID, or create a new profile below.`);
      } else {
        setError(friendlyErrorMessage(err));
      }
    }
  }

  return (
    <div className="cover">
      <CoverLandscape />
      <Link to="/" className="cover__brand" aria-label="CircadianIQ home">
        <BrandLockup />
      </Link>
      <div className="cover__ornament">
        <CoverOrnament />
      </div>

      <main className="cover__content">
        <CoverSun />
        <p className="cover__eyebrow">Your biological time atlas</p>
        <h1 className="cover__title">CircadianIQ</h1>
        <p className="cover__subtitle">Estimate · Understand · Align</p>
        <p className="cover__lede">A model-based view of your circadian rhythm from your daily behavior.</p>

        <form className="cover__form" onSubmit={handleSubmit} noValidate>
          <label htmlFor="participant-id" className="visually-hidden">
            Participant ID
          </label>
          <div className="input-with-icon">
            <Icon name="user" size={18} />
            <input
              id="participant-id"
              className="input input--pill"
              inputMode="numeric"
              autoComplete="off"
              value={participantId}
              onChange={(e) => {
                setParticipantId(e.target.value);
                if (error) setError(null);
              }}
              placeholder="Participant ID (e.g. 1)"
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? "participant-error" : undefined}
            />
          </div>
          <button type="submit" className="button button--primary" style={{ minHeight: 46, fontSize: 15 }} disabled={checking}>
            {checking ? "Opening your atlas…" : "View dashboard"}
            {!checking && <Icon name="arrow-right" size={16} />}
          </button>
          {error && (
            <p id="participant-error" className="form-message form-message--error" role="alert" style={{ justifyContent: "center" }}>
              {error}
            </p>
          )}
        </form>

        <p style={{ marginTop: 22, fontSize: 14 }}>
          New here? <Link to="/onboarding">Create a participant profile</Link>
        </p>
        <p style={{ marginTop: 10 }}>
          <Link to="/demo" className="cover__demo-link">
            30-Day Research Demo
          </Link>
        </p>
        <p className="cover__disclaimer">Estimated from behavioral patterns. Not a clinical measurement.</p>
      </main>

      <div className="cover__moons">
        <MoonPhases />
      </div>
    </div>
  );
}
