import { useState } from "react";
import { api } from "../api/client";
import { useAction } from "../hooks/useApi";
import { ErrorState } from "../components/ErrorState";
import { TimeField } from "../components/form/TimeField";
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
    <div className="card" style={{ maxWidth: 520, margin: "0 auto" }}>
      <nav aria-label="Onboarding progress" style={{ display: "flex", gap: 4, marginBottom: 20 }}>
        {STEP_ORDER.slice(0, -1).map((s, i) => (
          <span
            key={s}
            aria-hidden="true"
            style={{ height: 4, flex: 1, borderRadius: 2, background: i <= stepIndex ? "var(--color-accent)" : "var(--color-surface-muted)" }}
          />
        ))}
      </nav>

      {step === "welcome" && (
        <section>
          <h2>Welcome to CircadianIQ</h2>
          <p style={{ color: "var(--color-text-muted)", marginTop: 8 }}>
            CircadianIQ estimates your biological clock from your everyday behavior -- sleep, light, screens, meals, and
            exercise -- and helps you understand how well your routine matches it.
          </p>
          <button type="button" className="button button--primary" style={{ marginTop: 20 }} onClick={next}>
            Get started
          </button>
        </section>
      )}

      {step === "boundary" && (
        <section>
          <h2>Before we begin</h2>
          <p style={{ marginTop: 8 }}>{BOUNDARY_NOTE_FULL}</p>
          <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 16, fontSize: 14 }}>
            <input type="checkbox" id="ack-boundary" onChange={next} />I understand
          </label>
          <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
            <button type="button" className="button button--secondary" onClick={back}>
              Back
            </button>
          </div>
        </section>
      )}

      {step === "meq" && (
        <section>
          <h2>A quick preference question</h2>
          <p style={{ color: "var(--color-text-muted)", marginTop: 8 }}>
            On a scale from strongly &quot;morning person&quot; to strongly &quot;evening person,&quot; where do you fall?
          </p>
          <label htmlFor="meq-score" style={{ display: "block", marginTop: 16, fontSize: 13, color: "var(--color-text-muted)" }}>
            Morning-type <input
              id="meq-score"
              type="range"
              min={0}
              max={100}
              value={meqScore}
              onChange={(e) => setMeqScore(Number(e.target.value))}
              style={{ verticalAlign: "middle", margin: "0 10px" }}
            />{" "}
            Evening-type
          </label>
          <p style={{ fontSize: 12, color: "var(--color-text-faint)" }}>Current: {meqScore}</p>
          <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
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
          <p style={{ color: "var(--color-text-muted)", marginTop: 8 }}>
            On a day with no alarm or obligations, what time is the midpoint of your sleep? (Halfway between when you fall
            asleep and when you wake up.)
          </p>
          <div style={{ marginTop: 16 }}>
            <TimeField id="msfsc" label="Free-day sleep midpoint" value={msfscTime} onChange={setMsfscTime} />
          </div>
          <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
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
          <label htmlFor="participant-code" style={{ display: "block", marginTop: 12, fontSize: 13, color: "var(--color-text-muted)" }}>
            Choose a participant code
          </label>
          <input
            id="participant-code"
            value={participantCode}
            onChange={(e) => setParticipantCode(e.target.value)}
            placeholder="e.g. P000123"
            style={{ padding: "8px 10px", borderRadius: "var(--radius-sm)", border: "1px solid var(--color-border)", width: "100%", marginTop: 4 }}
          />
          <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
            <button type="button" className="button button--secondary" onClick={back}>
              Back
            </button>
            <button type="button" className="button button--primary" disabled={!participantCode || submitAction.loading} onClick={handleConfirm}>
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
          <p style={{ color: "var(--color-text-muted)", marginTop: 8 }}>{result.note}</p>
          <button type="button" className="button button--primary" style={{ marginTop: 20 }} onClick={() => onComplete(result.participant_id)}>
            Continue
          </button>
        </section>
      )}
    </div>
  );
}
