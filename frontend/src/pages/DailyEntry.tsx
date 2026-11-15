import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useAction, useFetch } from "../hooks/useApi";
import { ErrorState } from "../components/ErrorState";
import { NumberField } from "../components/form/NumberField";
import { TimeField } from "../components/form/TimeField";
import { Icon, type IconName } from "../components/atlas/Icon";
import { PageHeader } from "../components/layout/PageHeader";
import { DateNavigator } from "../components/layout/DateNavigator";
import { formatDateLong, todayIso } from "../utils/time";
import type { BehaviorEntry } from "../api/types";

/**
 * Manual daily behavioral logging -- sleep, light, screen, meals,
 * exercise, caffeine. Client-side validation is only for usability
 * (native time/number inputs); the backend remains authoritative and
 * re-validates everything.
 *
 * The selected date lives in the `?date=` query parameter so it stays
 * consistent with the dashboard. When a date already has a saved
 * entry, the values the behavior-history endpoint returns are
 * pre-filled into still-empty fields. The backend's save is an upsert
 * that ignores blank fields, so leaving a field empty keeps any value
 * saved earlier for that date.
 */
export function DailyEntry({ participantId }: { participantId: number }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const date = searchParams.get("date") ?? todayIso();
  const setDate = (next: string) => {
    const params = new URLSearchParams(searchParams);
    params.set("date", next);
    setSearchParams(params, { replace: true });
  };

  // Previously saved values for this date (existing behavior-history endpoint).
  const existing = useFetch(
    () => api.getBehaviorHistory(participantId, { start_date: date, end_date: date, limit: 1 }),
    [participantId, date],
  );
  const existingEntry: BehaviorEntry | null = existing.data?.entries.find((e) => e.date === date) ?? null;

  return (
    <div>
      <PageHeader
        title="Log today's behavior"
        subtitle="Record your key daily events for a more accurate rhythm estimate."
        actions={<DateNavigator id="entry-date" label="Date" value={date} onChange={setDate} />}
      />
      {/* Keyed by date: choosing another date starts a fresh form for it. */}
      <EntryForm
        key={date}
        participantId={participantId}
        date={date}
        existingEntry={existingEntry}
        existingLoading={existing.loading}
        existingFailed={Boolean(existing.error)}
        onSaved={existing.refetch}
      />
    </div>
  );
}

function EntryForm({
  participantId,
  date,
  existingEntry,
  existingLoading,
  existingFailed,
  onSaved,
}: {
  participantId: number;
  date: string;
  existingEntry: BehaviorEntry | null;
  existingLoading: boolean;
  existingFailed: boolean;
  onSaved: () => void;
}) {
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
  const [prefilled, setPrefilled] = useState(false);
  // Durations as displayed after pre-fill (rounded to whole minutes).
  const [shownLight, setShownLight] = useState<number | null>(null);
  const [shownScreen, setShownScreen] = useState<number | null>(null);

  // Once the saved entry for this date arrives, fill only fields that
  // are still empty (nothing already typed is overwritten). Done during
  // render -- React's pattern for adjusting state to new props.
  // Stored durations can carry long decimals; they are *shown* rounded,
  // and an untouched pre-filled duration is sent as null on save -- the
  // backend upsert keeps the stored value for null fields, so opening
  // and re-saving an entry never alters the stored precise value.
  if (existingEntry && !prefilled) {
    setPrefilled(true);
    const e = existingEntry;
    const light = e.morning_light_duration_minutes !== null ? Math.round(e.morning_light_duration_minutes) : null;
    const screen = e.evening_screen_duration_minutes !== null ? Math.round(e.evening_screen_duration_minutes) : null;
    setShownLight(light);
    setShownScreen(screen);
    if (e.sleep_onset) setSleepOnset((v) => v || e.sleep_onset || "");
    if (light !== null) setLightDuration((v) => (v === "" ? light : v));
    if (screen !== null) setScreenDuration((v) => (v === "" ? screen : v));
    if (e.last_meal_time) setLastMeal((v) => v || e.last_meal_time || "");
    if (e.exercise_time) setExercise((v) => v || e.exercise_time || "");
  }

  const saveAction = useAction(() =>
    api.recordDailyEntry(participantId, {
      observation_date: date,
      sleep_onset_time: sleepOnset || null,
      sleep_offset_time: sleepOffset || null,
      morning_light_start_time: lightStart || null,
      morning_light_duration_minutes: lightDuration === "" || lightDuration === shownLight ? null : lightDuration,
      evening_screen_end_time: screenEnd || null,
      evening_screen_duration_minutes: screenDuration === "" || screenDuration === shownScreen ? null : screenDuration,
      last_meal_time: lastMeal || null,
      exercise_time: exercise || null,
      last_caffeine_time: caffeine || null,
      caffeine_amount_mg: caffeineAmount === "" ? null : caffeineAmount,
    }),
  );

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (saveAction.loading) return;
    setSavedAt(null);
    try {
      const result = await saveAction.run();
      setSavedAt(result.observation_date);
      onSaved();
    } catch {
      // saveAction.error is rendered below.
    }
  }

  return (
    <form className="log-form" onSubmit={handleSubmit} aria-describedby="log-status">
      <p id="log-status" className="small muted" style={{ minHeight: 20 }}>
        {existingLoading
          ? "Checking for an earlier entry on this date…"
          : existingEntry
            ? `An entry already exists for ${formatDateLong(date)} — its saved values are filled in. Blank fields keep any earlier value.`
            : existingFailed
              ? "Earlier values for this date couldn't be loaded; you can still save a new entry."
              : `Logging for ${formatDateLong(date)}. Every field is optional.`}
      </p>

      <LogRow icon="bed" label="Sleep">
        <TimeField id="sleep-onset" label="Sleep onset" value={sleepOnset} onChange={setSleepOnset} />
        <TimeField id="sleep-offset" label="Wake time" value={sleepOffset} onChange={setSleepOffset} />
      </LogRow>

      <LogRow icon="sun" label="Light">
        <TimeField id="light-start" label="Morning light start" value={lightStart} onChange={setLightStart} />
        <NumberField id="light-duration" label="Duration (minutes)" min={0} max={600} value={lightDuration} onChange={setLightDuration} />
      </LogRow>

      <LogRow icon="monitor" label="Screen">
        <TimeField id="screen-end" label="Evening screen end" value={screenEnd} onChange={setScreenEnd} />
        <NumberField
          id="screen-duration"
          label="Duration (minutes)"
          min={0}
          max={1440}
          value={screenDuration}
          onChange={setScreenDuration}
        />
      </LogRow>

      <LogRow icon="cutlery" label="Meals & exercise">
        <TimeField id="last-meal" label="Last meal" value={lastMeal} onChange={setLastMeal} />
        <TimeField id="exercise" label="Exercise" value={exercise} onChange={setExercise} />
      </LogRow>

      <LogRow icon="cup" label="Caffeine">
        <TimeField id="caffeine-time" label="Last caffeine" value={caffeine} onChange={setCaffeine} />
        <NumberField id="caffeine-amount" label="Amount (mg)" min={0} max={2000} value={caffeineAmount} onChange={setCaffeineAmount} />
      </LogRow>

      <div className="log-actions">
        <button type="submit" className="button button--primary button--wide button--caps" disabled={saveAction.loading}>
          {saveAction.loading ? "Saving…" : "Save today's entry"}
          {!saveAction.loading && <Icon name="arrow-right" size={16} />}
        </button>

        {savedAt && !saveAction.loading && (
          <p className="form-message form-message--success" role="status">
            <Icon name="check" size={16} />
            <span>
              Saved {savedAt}. <Link to={`/dashboard/${participantId}?date=${savedAt}`}>View dashboard</Link> — use &ldquo;Update
              today&apos;s estimate&rdquo; there to include it.
            </span>
          </p>
        )}
        {saveAction.error && (
          <div style={{ width: "100%", maxWidth: 560 }}>
            <ErrorState error={saveAction.error} />
          </div>
        )}
      </div>
    </form>
  );
}

function LogRow({ icon, label, children }: { icon: IconName; label: string; children: React.ReactNode }) {
  return (
    <fieldset className="log-row" style={{ border: "none", borderBottom: "1px solid var(--sand)" }}>
      <legend className="visually-hidden">{label}</legend>
      <span className="log-row__label" aria-hidden="true">
        <Icon name={icon} size={24} strokeWidth={1.4} />
        {label}
      </span>
      {children}
    </fieldset>
  );
}
