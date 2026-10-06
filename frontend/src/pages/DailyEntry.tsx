import { useState } from "react";
import { api } from "../api/client";
import { useAction } from "../hooks/useApi";
import { ErrorState } from "../components/ErrorState";
import { NumberField } from "../components/form/NumberField";
import { TimeField } from "../components/form/TimeField";

/**
 * Manual daily behavioral logging -- sleep, light, screen, meals,
 * exercise, caffeine. Client-side validation is only for usability
 * (native time/number inputs); the backend remains authoritative and
 * re-validates everything.
 */
export function DailyEntry({ participantId }: { participantId: number }) {
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [sleepOnset, setSleepOnset] = useState("");
  const [sleepOffset, setSleepOffset] = useState("");
  const [lightStart, setLightStart] = useState("");
  const [lightDuration, setLightDuration] = useState<number | "">("");
  const [screenEnd, setScreenEnd] = useState("");
  const [screenDuration, setScreenDuration] = useState<number | "">("");
  const [lastMeal, setLastMeal] = useState("");
  const [exercise, setExercise] = useState("");
  const [caffeine, setCaffeine] = useState("");
  const [caffeineAmount, setCaffeineAmount] = useState<number | "">("");
  const [savedAt, setSavedAt] = useState<string | null>(null);

  const saveAction = useAction(() => api.recordDailyEntry(participantId, {
    observation_date: date,
    sleep_onset_time: sleepOnset || null,
    sleep_offset_time: sleepOffset || null,
    morning_light_start_time: lightStart || null,
    morning_light_duration_minutes: lightDuration === "" ? null : lightDuration,
    evening_screen_end_time: screenEnd || null,
    evening_screen_duration_minutes: screenDuration === "" ? null : screenDuration,
    last_meal_time: lastMeal || null,
    exercise_time: exercise || null,
    last_caffeine_time: caffeine || null,
    caffeine_amount_mg: caffeineAmount === "" ? null : caffeineAmount,
  }));

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSavedAt(null);
    const result = await saveAction.run();
    setSavedAt(result.observation_date);
  }

  return (
    <form className="card" onSubmit={handleSubmit} style={{ maxWidth: 560, display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <div className="section-label">Log today&apos;s behavior</div>
        <label htmlFor="entry-date" style={{ fontSize: 13, color: "var(--color-text-muted)", display: "block", marginBottom: 4 }}>
          Date
        </label>
        <input id="entry-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} style={{ padding: "8px 10px", borderRadius: "var(--radius-sm)", border: "1px solid var(--color-border)" }} />
      </div>

      <fieldset style={{ border: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 10 }}>
        <legend className="section-label">Sleep</legend>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <TimeField id="sleep-onset" label="Sleep onset" value={sleepOnset} onChange={setSleepOnset} />
          <TimeField id="sleep-offset" label="Wake time" value={sleepOffset} onChange={setSleepOffset} />
        </div>
      </fieldset>

      <fieldset style={{ border: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 10 }}>
        <legend className="section-label">Light</legend>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <TimeField id="light-start" label="Morning light start" value={lightStart} onChange={setLightStart} />
          <NumberField id="light-duration" label="Duration (minutes)" min={0} max={600} value={lightDuration} onChange={setLightDuration} />
        </div>
      </fieldset>

      <fieldset style={{ border: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 10 }}>
        <legend className="section-label">Screen</legend>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <TimeField id="screen-end" label="Evening screen end" value={screenEnd} onChange={setScreenEnd} />
          <NumberField id="screen-duration" label="Duration (minutes)" min={0} max={1440} value={screenDuration} onChange={setScreenDuration} />
        </div>
      </fieldset>

      <fieldset style={{ border: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 10 }}>
        <legend className="section-label">Meals &amp; exercise</legend>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <TimeField id="last-meal" label="Last meal" value={lastMeal} onChange={setLastMeal} />
          <TimeField id="exercise" label="Exercise" value={exercise} onChange={setExercise} />
        </div>
      </fieldset>

      <fieldset style={{ border: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 10 }}>
        <legend className="section-label">Caffeine</legend>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <TimeField id="caffeine-time" label="Last caffeine" value={caffeine} onChange={setCaffeine} />
          <NumberField id="caffeine-amount" label="Amount (mg)" min={0} max={2000} value={caffeineAmount} onChange={setCaffeineAmount} />
        </div>
      </fieldset>

      <button type="submit" className="button button--primary" disabled={saveAction.loading}>
        {saveAction.loading ? "Saving…" : "Save today's entry"}
      </button>

      {savedAt && !saveAction.loading && <p style={{ color: "var(--color-good)", fontSize: 13 }}>Saved {savedAt}.</p>}
      {saveAction.error && <ErrorState error={saveAction.error} />}
    </form>
  );
}
