import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAction } from "../hooks/useApi";
import { ErrorState } from "../components/ErrorState";
import { TimeField } from "../components/form/TimeField";
import { BrandLockup } from "../components/atlas/BrandMark";
import { Icon } from "../components/atlas/Icon";
import { CoverLandscape } from "../components/atlas/Illustrations";
import { BOUNDARY_NOTE_FULL } from "../utils/messages";
import type { OnboardingResponse } from "../api/types";

type Step = "welcome" | "boundary" | "meq" | "mctq" | "confirm" | "done";

const STEP_ORDER: Step[] = ["welcome", "boundary", "meq", "mctq", "confirm", "done"];

/**
 * A simple, linear onboarding flow. Only collects what the backend
 * onboarding endpoint actually accepts (participant_code, chronotype,
 * meq_score, msfsc_time) -- see docs/ui_architecture.md "Onboarding
 * flow" for why a full item-level MEQ/MCTQ questionnaire isn't
 * rendered here (Phase 15 does not currently expose a structured
 * question schema, and the frontend must not invent MEQ/MCTQ scoring
 * logic itself).
 */
export function Onboarding({ onComplete }: { onComplete: (participantId: number) => void }) {
  const [step, setStep] = useState<Step>("welcome");
  const [participantCode, setParticipantCode] = useState("");
  const [meqScore, setMeqScore] = useState(50);
  const [msfscTime, setMsfscTime] = useState("");
  const [result, setResult] = useState<OnboardingResponse | null>(null);

  const submitAction = useAction(() =>
    api.onboardParticipant({
      participant_code: participantCode,
      meq_score: meqScore,
      msfsc_time: msfscTime || null,
    }),
  );

  const stepIndex = STEP_ORDER.indexOf(step);
  const next = () => setStep(STEP_ORDER[Math.min(stepIndex + 1, STEP_ORDER.length - 1)]);
  const back = () => setStep(STEP_ORDER[Math.max(stepIndex - 1, 0)]);

  async function handleConfirm() {
    try {
      const response = await submitAction.run();
      setResult(response);
      setStep("done");
    } catch {
      // submitAction already captured the error for display; nothing
      // further to do here.
    }
  }

  return (
    <div className="cover__panel onboarding">
      <nav aria-label="Onboarding progress" className="step-track">
        {STEP_ORDER.slice(0, -1).map((s, i) => (
          <span key={s} aria-hidden="true" data-done={i <= stepIndex ? "true" : "false"} />
        ))}
      </nav>

      {step === "welcome" && (
        <section>
          <h2>Welcome to CircadianIQ</h2>
          <p className="muted" style={{ marginTop: 10 }}>
            CircadianIQ estimates your biological clock from your everyday behavior — sleep, light, screens, meals, and exercise — and
            helps you understand how well your routine matches it.
          </p>
          <button type="button" className="button button--primary" style={{ marginTop: 24 }} onClick={next}>
            Get started
          </button>
        </section>
      )}

      {step === "boundary" && (
        <section>
          <h2>Before we begin</h2>
          <p style={{ marginTop: 10 }}>{BOUNDARY_NOTE_FULL}</p>
          <label style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 18, fontSize: 14 }}>
            <input type="checkbox" id="ack-boundary" onChange={next} style={{ width: 16, height: 16, accentColor: "var(--evergreen)" }} />I
            understand
          </label>
          <div style={{ marginTop: 22, display: "flex", gap: 10 }}>
            <button type="button" className="button button--secondary" onClick={back}>
              Back
            </button>
          </div>
        </section>
      )}

      {step === "meq" && (
        <section>
          <h2>A quick preference question</h2>
          <p className="muted" style={{ marginTop: 10 }}>
            On a scale from strongly &quot;morning person&quot; to strongly &quot;evening person,&quot; where do you fall?
          </p>
          <label htmlFor="meq-score" style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 20, fontSize: 13 }}>
            <span className="muted">Morning-type</span>
            <input
              id="meq-score"
              className="range-input"
              type="range"
              min={0}
              max={100}
              value={meqScore}
              onChange={(e) => setMeqScore(Number(e.target.value))}
              style={{ flex: 1 }}
            />
            <span className="muted">Evening-type</span>
          </label>
          <p className="small muted" style={{ marginTop: 6 }}>
            Current: {meqScore}
          </p>
          <div style={{ marginTop: 22, display: "flex", gap: 10 }}>
            <button type="button" className="button button--secondary" onClick={back}>
              Back
            </button>
            <button type="button" className="button button--primary" onClick={next}>
              Continue
            </button>
          </div>
        </section>
      )}

      {step === "mctq" && (
        <section>
          <h2>Your free-day sleep</h2>
          <p className="muted" style={{ marginTop: 10 }}>
            On a day with no alarm or obligations, what time is the midpoint of your sleep? (Halfway between when you fall asleep and when
            you wake up.)
          </p>
          <div style={{ marginTop: 18, maxWidth: 240 }}>
            <TimeField id="msfsc" label="Free-day sleep midpoint" value={msfscTime} onChange={setMsfscTime} />
          </div>
          <div style={{ marginTop: 22, display: "flex", gap: 10 }}>
            <button type="button" className="button button--secondary" onClick={back}>
              Back
            </button>
            <button type="button" className="button button--primary" onClick={next}>
              Continue
            </button>
          </div>
        </section>
      )}

      {step === "confirm" && (
        <section>
          <h2>Create your profile</h2>
          <div className="field" style={{ marginTop: 16 }}>
            <label htmlFor="participant-code">Choose a participant code</label>
            <input
              id="participant-code"
              className="input"
              value={participantCode}
              onChange={(e) => setParticipantCode(e.target.value)}
              placeholder="e.g. P000123"
            />
          </div>
          <div style={{ marginTop: 22, display: "flex", gap: 10 }}>
            <button type="button" className="button button--secondary" onClick={back}>
              Back
            </button>
            <button
              type="button"
              className="button button--primary"
              disabled={!participantCode || submitAction.loading}
              onClick={handleConfirm}
            >
              {submitAction.loading ? "Creating…" : "Finish"}
            </button>
          </div>
          {submitAction.error && (
            <div style={{ marginTop: 16 }}>
              <ErrorState error={submitAction.error} />
            </div>
          )}
        </section>
      )}

      {step === "done" && result && (
        <section>
          <h2>You&apos;re all set, {result.participant_code}</h2>
          <p className="muted" style={{ marginTop: 10 }}>
            {result.note}
          </p>
          <p className="small muted" style={{ marginTop: 8 }}>
            Your participant ID is <strong style={{ color: "var(--ink)" }}>{result.participant_id}</strong> — use it to return to your
            dashboard.
          </p>
          <button
            type="button"
            className="button button--primary"
            style={{ marginTop: 22 }}
            onClick={() => onComplete(result.participant_id)}
          >
            Continue
            <Icon name="arrow-right" size={16} />
          </button>
        </section>
      )}
    </div>
  );
}

/** The onboarding route: the atlas-cover composition around the
 * onboarding panel (kept separate so the panel itself stays usable
 * outside a router, e.g. in isolated component tests). */
export function OnboardingPage({ onComplete }: { onComplete: (participantId: number) => void }) {
  return (
    <div className="cover">
      <CoverLandscape />
      <Link to="/" className="cover__brand" aria-label="CircadianIQ home">
        <BrandLockup />
      </Link>

      <main className="cover__content" style={{ paddingTop: "4vh" }}>
        <p className="cover__eyebrow" style={{ fontSize: 15 }}>
          New participant profile
        </p>
        <Onboarding onComplete={onComplete} />
        <p style={{ marginTop: 18, fontSize: 14 }}>
          Already enrolled? <Link to="/">Enter your participant ID</Link>
        </p>
      </main>
    </div>
  );
}
