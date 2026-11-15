import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { BehaviorEntry, CircadianHistoryEntry, InterventionHistoryEntry, StatusResponse } from "../api/types";
import { useFetch } from "../hooks/useApi";
import { useDailyStatuses } from "../hooks/useDailyStatuses";
import { useParticipant } from "../hooks/useParticipant";
import { ClockVisualization } from "../components/ClockVisualization";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { ContributorEvolution } from "../components/ContributorEvolution";
import { ErrorState, InlineNotice } from "../components/ErrorState";
import { JourneyChart } from "../components/JourneyChart";
import { LoadingState, SkeletonLines } from "../components/LoadingState";
import { Icon } from "../components/atlas/Icon";
import { iconForSignal } from "../components/atlas/signals";
import { PageHeader } from "../components/layout/PageHeader";
import { DEMO_DAYS, DEMO_PARTICIPANT_CODE, DEMO_PARTICIPANT_ID, SYNTHETIC_LABEL, WARMUP_DAYS, isDemoParticipantCode } from "../config/demo";
import { CAUSAL_CAVEAT } from "../utils/messages";
import { MEASUREMENT_PHASE_LABELS, contributorLabel, directionShortLabel, flagTypeLabel } from "../utils/terminology";
import { addDaysIso, formatDateLong, formatDuration, formatTargetDisplay, parseClockHour, to12Hour } from "../utils/time";

const PLAY_INTERVAL_MS = 1600;

/** `/demo`: locate DEMO-001 and confirm its identity before opening the journey. */
export function ResearchDemoEntry() {
  const { participant, error, loading } = useParticipant(DEMO_PARTICIPANT_ID);
  if (loading) return <LoadingState label="Locating the research demonstration participant…" />;
  if (error) {
    const notSeeded = error instanceof ApiError && error.status === 404;
    return (
      <div>
        <PageHeader title="30-day research demo" subtitle="A database-backed replay of one synthetic participant's journey." />
        {notSeeded ? <NotSeeded /> : <ErrorState error={error} />}
      </div>
    );
  }
  if (!participant || !isDemoParticipantCode(participant.participant_code)) {
    return (
      <div>
        <PageHeader title="30-day research demo" />
        <div className="notice notice--moderate">
          <p>
            Participant #{DEMO_PARTICIPANT_ID} in this database is <strong>{participant?.participant_code}</strong>, not {DEMO_PARTICIPANT_CODE}. The
            demonstration will not present another record as the synthetic participant.
          </p>
        </div>
      </div>
    );
  }
  return <Navigate to={`/demo/${participant.participant_id}`} replace />;
}

function NotSeeded() {
  return (
    <div className="empty-state" style={{ paddingTop: 0 }}>
      <span className="empty-state__title">{DEMO_PARTICIPANT_CODE} has not been seeded in this database</span>
      <p>Create it with the one-time seeding utility, then reload this page:</p>
      <pre className="code-block">python scripts/demo/seed_demo_participant.py --dry-run{"\n"}python scripts/demo/seed_demo_participant.py</pre>
    </div>
  );
}

type DayKind = "warmup" | "prediction" | "no-result";

/**
 * The 30-Day Circadian Journey (Research Mode). Everything shown is
 * read from the existing API -- observations (GET /behavior), daily
 * results (GET /circadian/history and GET /status?target_date= per
 * day), interventions (GET /interventions). Navigating days never
 * re-runs inference; per-day results are fetched once and cached.
 */
export function ResearchDemo({ participantId }: { participantId: number }) {
  const { participant, error: participantError, loading: participantLoading } = useParticipant(participantId);
  const [searchParams, setSearchParams] = useSearchParams();
  const [playing, setPlaying] = useState(false);

  const day = clampDay(Number(searchParams.get("day") ?? 1));
  const setDay = (next: number) => {
    const params = new URLSearchParams(searchParams);
    params.set("day", String(clampDay(next)));
    setSearchParams(params, { replace: true });
  };

  const start = participant?.enrollment_date ?? null;
  const end = start ? addDaysIso(start, DEMO_DAYS - 1) : null;
  const dates = useMemo(() => (start ? Array.from({ length: DEMO_DAYS }, (_, i) => addDaysIso(start, i)) : []), [start]);
  const isDemo = isDemoParticipantCode(participant?.participant_code);
  const ready = Boolean(start && isDemo);

  const range = { start_date: start ?? undefined, end_date: end ?? undefined };
  const behavior = useFetch(() => api.getBehaviorHistory(participantId, { ...range, limit: DEMO_DAYS }), [participantId, start], ready);
  const history = useFetch(() => api.getCircadianHistory(participantId, { ...range, limit: DEMO_DAYS }), [participantId, start], ready);
  const interventions = useFetch(() => api.getInterventionHistory(participantId, { ...range, limit: 60 }), [participantId, start], ready);

  const behaviorByDate = useMemo(() => indexBy(behavior.data?.entries ?? [], (e) => e.date), [behavior.data]);
  const historyByDate = useMemo(() => indexBy(history.data?.entries ?? [], (e) => e.date), [history.data]);
  const interventionByDate = useMemo(() => indexBy(interventions.data?.entries ?? [], (e) => e.log_date), [interventions.data]);
  const predictionDates = useMemo(() => dates.filter((d) => historyByDate[d]?.biological_clock), [dates, historyByDate]);
  const statuses = useDailyStatuses(participantId, ready ? predictionDates : []);

  // Play / pause: one timer per day -- after the pause, advance once; the
  // effect re-arms for the new day, and stops on the last day.
  useEffect(() => {
    if (!playing) return;
    const timer = window.setTimeout(() => {
      if (day >= DEMO_DAYS) setPlaying(false);
      else setDay(day + 1);
    }, PLAY_INTERVAL_MS);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, day]);

  if (participantLoading) return <LoadingState label="Loading the research participant…" />;
  if (participantError) return <ErrorState error={participantError} />;
  if (!participant || !isDemo) {
    return (
      <div>
        <PageHeader title="30-day research demo" />
        <div className="notice notice--moderate">
          <p>
            Participant #{participantId} ({participant?.participant_code}) is not the {DEMO_PARTICIPANT_CODE} research demonstration participant.{" "}
            <Link to="/demo">Open the demonstration</Link>
          </p>
        </div>
      </div>
    );
  }

  const kindOf = (d: number): DayKind => (d <= WARMUP_DAYS ? "warmup" : historyByDate[dates[d - 1]]?.biological_clock ? "prediction" : "no-result");
  const date = dates[day - 1];
  const kind = kindOf(day);
  const status = statuses.byDate[date];
  const loadingCore = behavior.loading || history.loading;

  const valuesByDay = <T,>(source: Record<string, T>, read: (row: T) => number | null) =>
    dates.map((d) => (source[d] ? read(source[d]) : null));

  return (
    <div className="journey">
      <PageHeader
        title="30-day circadian journey"
        subtitle="Research Mode · a database-backed replay of one synthetic participant, processed day by day by the CircadianIQ pipeline."
        actions={<span className="badge badge--moderate synthetic-badge">{SYNTHETIC_LABEL}</span>}
      />

      {/* 8.1 overview */}
      <dl className="journey-overview">
        <Fact label="Participant" value={participant.participant_code} sub={`#${participant.participant_id} · ${participant.chronotype ?? "chronotype —"}`} />
        <Fact label="Observation period" value={`${formatDateLong(start)} – ${formatDateLong(end)}`} sub={`${DEMO_DAYS} consecutive days`} />
        <Fact label="Recorded behavioral days" value={behavior.data ? String(behavior.data.count) : "…"} sub="daily_observations" />
        <Fact label="Valid prediction days" value={history.data ? String(predictionDates.length) : "…"} sub={`days ${WARMUP_DAYS + 1}–${DEMO_DAYS} eligible`} />
        <Fact label="Selected day" value={`Day ${day} / ${DEMO_DAYS}`} sub={formatDateLong(date)} />
      </dl>

      {/* 8.2 navigation */}
      <section className="journey-nav" aria-label="Day navigation">
        <div className="journey-nav__controls">
          <button type="button" className="icon-button" aria-label="Previous day" disabled={day <= 1} onClick={() => setDay(day - 1)}>
            <Icon name="chevron-left" size={18} />
          </button>
          <button type="button" className="button button--primary button--small" onClick={() => setPlaying((p) => !p)} aria-pressed={playing}>
            {playing ? "Pause" : day >= DEMO_DAYS ? "Replay" : "Play"}
          </button>
          <button type="button" className="icon-button" aria-label="Next day" disabled={day >= DEMO_DAYS} onClick={() => setDay(day + 1)}>
            <Icon name="chevron-right" size={18} />
          </button>
          <label className="small muted" htmlFor="journey-day">
            Day
          </label>
          <select
            id="journey-day"
            className="input"
            style={{ width: 92, height: 32, padding: "2px 8px" }}
            value={day}
            onChange={(e) => setDay(Number(e.target.value))}
          >
            {dates.map((d, i) => (
              <option key={d} value={i + 1}>
                {i + 1}
              </option>
            ))}
          </select>
          <span className="journey-nav__counter serif" aria-live="polite">
            Day {day} / {DEMO_DAYS}
          </span>
        </div>
        <ol className="journey-strip">
          {dates.map((d, i) => {
            const k = kindOf(i + 1);
            return (
              <li key={d}>
                <button
                  type="button"
                  className={`journey-strip__day journey-strip__day--${k}${i + 1 === day ? " is-selected" : ""}`}
                  aria-current={i + 1 === day ? "step" : undefined}
                  aria-label={`Day ${i + 1}, ${formatDateLong(d)}: ${k === "warmup" ? "warm-up" : k === "prediction" ? "prediction" : "no persisted result"}`}
                  onClick={() => {
                    if (playing && i + 1 === day) setPlaying(false);
                    setDay(i + 1);
                  }}
                >
                  {i + 1}
                </button>
              </li>
            );
          })}
        </ol>
        <p className="journey-legend small muted">
          <span className="journey-strip__swatch journey-strip__day--warmup" /> Warm-up (days 1–{WARMUP_DAYS})
          <span className="journey-strip__swatch journey-strip__day--prediction" /> Persisted prediction
          <span className="journey-strip__swatch journey-strip__day--no-result" /> No persisted result
        </p>
      </section>

      {loadingCore && !behavior.data ? (
        <LoadingState label="Loading the 30-day record…" />
      ) : behavior.error || history.error ? (
        <ErrorState error={behavior.error ?? history.error} onRetry={() => (behavior.error ? behavior.refetch() : history.refetch())} />
      ) : (
        <>
          <div className="ruled-row journey-day">
            <ObservationPanel day={day} date={date} entry={behaviorByDate[date]} />
            <InferencePanel
              day={day}
              kind={kind}
              historyEntry={historyByDate[date]}
              status={status}
              statusFailed={statuses.failed.includes(date)}
              intervention={interventionByDate[date]}
              participantId={participantId}
              date={date}
            />
          </div>

          {/* 8.5 trends */}
          <section className="atlas-section" aria-labelledby="trends-heading">
            <div className="section-label" id="trends-heading">
              Journey trends · persisted values by day
            </div>
            <div className="journey-charts">
              <JourneyChart
                title="Estimated DLMO (fused)"
                kind="clock"
                colorVar="--evergreen"
                values={valuesByDay(historyByDate, (e) => parseClockHour(e.biological_clock))}
                selectedIndex={day - 1}
                warmupCount={WARMUP_DAYS}
                onSelect={(i) => setDay(i + 1)}
              />
              <JourneyChart
                title="Alignment score"
                kind="score"
                colorVar="--teal"
                values={valuesByDay(historyByDate, (e) => e.alignment_score)}
                selectedIndex={day - 1}
                warmupCount={WARMUP_DAYS}
                onSelect={(i) => setDay(i + 1)}
              />
              <JourneyChart
                title="Confidence"
                kind="score"
                colorVar="--brown"
                values={valuesByDay(historyByDate, (e) => e.confidence_score)}
                selectedIndex={day - 1}
                warmupCount={WARMUP_DAYS}
                onSelect={(i) => setDay(i + 1)}
              />
              <JourneyChart
                title="Sleep onset"
                kind="clock"
                colorVar="--sig-sleep"
                values={valuesByDay(behaviorByDate, (e) => parseClockHour(e.sleep_onset))}
                selectedIndex={day - 1}
                warmupCount={0}
                onSelect={(i) => setDay(i + 1)}
              />
              <JourneyChart
                title="Morning light"
                kind="amount"
                unit="min"
                colorVar="--sig-light"
                values={valuesByDay(behaviorByDate, (e) => e.morning_light_duration_minutes)}
                selectedIndex={day - 1}
                warmupCount={0}
                onSelect={(i) => setDay(i + 1)}
              />
              <JourneyChart
                title="Evening screens"
                kind="amount"
                unit="min"
                colorVar="--sig-screen"
                values={valuesByDay(behaviorByDate, (e) => e.evening_screen_duration_minutes)}
                selectedIndex={day - 1}
                warmupCount={0}
                onSelect={(i) => setDay(i + 1)}
              />
              <JourneyChart
                title="Last meal"
                kind="clock"
                colorVar="--sig-meal"
                values={valuesByDay(behaviorByDate, (e) => parseClockHour(e.last_meal_time))}
                selectedIndex={day - 1}
                warmupCount={0}
                onSelect={(i) => setDay(i + 1)}
              />
              <JourneyChart
                title="Followed the day's recommendation"
                kind="score"
                unit="%"
                colorVar="--burnt"
                values={valuesByDay(interventionByDate, (e) => (e.compliance_degree === null ? null : Math.round(e.compliance_degree * 100)))}
                selectedIndex={day - 1}
                warmupCount={WARMUP_DAYS}
                onSelect={(i) => setDay(i + 1)}
              />
            </div>
            <p className="small muted" style={{ marginTop: 6 }}>
              Evening screen <em>end time</em> is stored for every day but the behavior API returns only the duration, so duration is charted. Click a point
              to select that day.
            </p>
          </section>

          {/* 8.6 contributor evolution */}
          <section className="atlas-section" aria-labelledby="evolution-heading">
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "baseline" }}>
              <div className="section-label" id="evolution-heading">
                Contributor evolution · daily top three ranking
              </div>
              {statuses.loaded < statuses.total && (
                <span className="small muted" role="status">
                  Loading daily results {statuses.loaded} / {statuses.total}…
                </span>
              )}
            </div>
            <ContributorEvolution
              days={predictionDates.map((d) => ({ day: dates.indexOf(d) + 1, date: d, status: statuses.byDate[d] }))}
              selectedDay={day}
              onSelect={setDay}
            />
            <p className="small muted" style={{ marginTop: 8, fontStyle: "italic" }}>
              Contributors reflect modeled influence within CircadianIQ, not a proven physiological cause.
            </p>
          </section>

          {/* 8.7 + 8.8 recommendations and intervention tracking */}
          <section className="atlas-section" aria-labelledby="recs-heading">
            <div className="section-label" id="recs-heading">
              Recommendation history & intervention tracking
            </div>
            {interventions.error ? (
              <InlineNotice error={interventions.error} label="Intervention records couldn't be loaded." onRetry={interventions.refetch} />
            ) : (
              <RecommendationHistory
                dates={predictionDates}
                allDates={dates}
                statuses={statuses.byDate}
                interventionByDate={interventionByDate}
                selectedDate={date}
                onSelect={(d) => setDay(dates.indexOf(d) + 1)}
              />
            )}
          </section>

          <Limitations />
        </>
      )}
    </div>
  );
}

function clampDay(value: number): number {
  return Number.isFinite(value) ? Math.min(DEMO_DAYS, Math.max(1, Math.round(value))) : 1;
}

function indexBy<T>(rows: T[], key: (row: T) => string): Record<string, T> {
  const out: Record<string, T> = {};
  for (const row of rows) out[key(row)] = row;
  return out;
}

function Fact({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <dt className="small muted">{label}</dt>
      <dd className="serif" style={{ margin: 0, fontSize: 19, fontWeight: 600, lineHeight: 1.2 }}>
        {value}
      </dd>
      {sub && <dd className="small muted" style={{ margin: 0 }}>{sub}</dd>}
    </div>
  );
}

/* ---------------- 8.3 daily observation panel ---------------- */

function ObservationPanel({ day, date, entry }: { day: number; date: string; entry: BehaviorEntry | undefined }) {
  const rows: Array<{ icon: Parameters<typeof Icon>[0]["name"]; label: string; value: string }> = entry
    ? [
        { icon: "bed", label: "Sleep onset", value: entry.sleep_onset ? to12Hour(entry.sleep_onset) : "Not logged" },
        { icon: "sun", label: "Morning light", value: entry.morning_light_duration_minutes !== null ? formatDuration(entry.morning_light_duration_minutes) : "Not logged" },
        { icon: "monitor", label: "Evening screens", value: entry.evening_screen_duration_minutes !== null ? formatDuration(entry.evening_screen_duration_minutes) : "Not logged" },
        { icon: "cutlery", label: "Last meal", value: entry.last_meal_time ? to12Hour(entry.last_meal_time) : "Not logged" },
        { icon: "activity", label: "Exercise", value: entry.exercise_time ? to12Hour(entry.exercise_time) : "Not logged" },
        { icon: "calendar", label: "Day type", value: entry.is_free_day === null ? "—" : entry.is_free_day ? "Free day" : "Work day" },
      ]
    : [];
  return (
    <section aria-labelledby="obs-heading">
      <div className="section-label" id="obs-heading">
        Recorded behavior · day {day}
      </div>
      <p className="small muted" style={{ marginBottom: 10 }}>
        {formatDateLong(date)} · as stored in daily_observations
      </p>
      {!entry ? (
        <p className="muted">No observation is stored for this date.</p>
      ) : (
        <ul className="obs-list">
          {rows.map((r) => (
            <li key={r.label}>
              <Icon name={r.icon} size={16} />
              <span>{r.label}</span>
              <strong>{r.value}</strong>
            </li>
          ))}
        </ul>
      )}
      <p className="small muted" style={{ marginTop: 10 }}>
        Also stored for this day but not returned by the behavior API: wake time, light start, screen end time, last caffeine and amount, exercise
        duration.
      </p>
    </section>
  );
}

/* ---------------- 8.4 daily inference panel ---------------- */

function InferencePanel({
  day,
  kind,
  historyEntry,
  status,
  statusFailed,
  intervention,
  participantId,
  date,
}: {
  day: number;
  kind: DayKind;
  historyEntry: CircadianHistoryEntry | undefined;
  status: StatusResponse | undefined;
  statusFailed: boolean;
  intervention: InterventionHistoryEntry | undefined;
  participantId: number;
  date: string;
}) {
  if (kind === "warmup") {
    return (
      <section aria-labelledby="inf-heading">
        <div className="section-label" id="inf-heading">
          CircadianIQ output · day {day}
        </div>
        <div className="empty-state" style={{ paddingTop: 0 }}>
          <span className="empty-state__title">Historical warm-up — six complete days required before the first prediction.</span>
          <p>
            Day {day} of {WARMUP_DAYS} is part of the context window. The first estimate is made on day {WARMUP_DAYS + 1}, from days 1–{WARMUP_DAYS}; no
            estimate is stored for this day.
          </p>
        </div>
      </section>
    );
  }
  if (kind === "no-result") {
    return (
      <section aria-labelledby="inf-heading">
        <div className="section-label" id="inf-heading">
          CircadianIQ output · day {day}
        </div>
        <p className="muted">No persisted result exists for this date.</p>
      </section>
    );
  }
  if (!status) {
    return (
      <section aria-labelledby="inf-heading">
        <div className="section-label" id="inf-heading">
          CircadianIQ output · day {day}
        </div>
        {statusFailed ? <p className="muted">This day&apos;s stored result couldn&apos;t be loaded.</p> : <SkeletonLines lines={6} />}
      </section>
    );
  }

  const markers = [
    { key: "dlmo", label: "Estimated DLMO (fused)", value: status.biological_clock, shape: "diamond" as const, colorVar: "--rust" },
    { key: "ideal", label: "Ideal sleep onset", value: status.alignment.ideal_sleep_onset, shape: "circle" as const, colorVar: "--teal" },
    { key: "actual", label: "Actual recent sleep onset", value: status.alignment.actual_sleep_onset, shape: "square" as const, colorVar: "--burnt" },
  ];
  const rec = status.recommendation;

  return (
    <section aria-labelledby="inf-heading">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", alignItems: "baseline" }}>
        <div className="section-label" id="inf-heading">
          CircadianIQ output · day {day}
        </div>
        <Link className="small" to={`/dashboard/${participantId}?date=${date}`}>
          Open on dashboard →
        </Link>
      </div>
      <ClockVisualization size={230} markers={markers} />

      <dl className="inference-facts">
        <div>
          <dt>Fusion</dt>
          <dd>
            Estimators&apos; disagreement: <strong>{historyEntry?.disagreement_regime ?? "—"}</strong>
          </dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>
            <ConfidenceBadge confidence={status.confidence} />
          </dd>
        </div>
        <div>
          <dt>Alignment</dt>
          <dd>
            <strong className="serif" style={{ fontSize: 22 }}>
              {status.alignment.score !== null ? Math.round(status.alignment.score) : "—"}
            </strong>{" "}
            / 100 · phase {status.alignment.phase_score !== null ? Math.round(status.alignment.phase_score) : "—"} · behavioral{" "}
            {status.alignment.behavioral_score !== null ? Math.round(status.alignment.behavioral_score) : "—"}
          </dd>
        </div>
        <div>
          <dt>Top contributors</dt>
          <dd>
            {status.contributors.length === 0 ? (
              "None ranked"
            ) : (
              <ol className="mini-ranking">
                {status.contributors.slice(0, 3).map((c) => (
                  <li key={c.signal}>
                    <Icon name={iconForSignal(c.signal)} size={14} /> {contributorLabel(c.signal)}
                    <span className="muted"> · {directionShortLabel(c.direction) ?? "—"}</span>
                  </li>
                ))}
              </ol>
            )}
          </dd>
        </div>
        <div>
          <dt>Recommendation</dt>
          <dd>
            {rec.suppressed ? (
              <span>Suppressed by the safety layer for this day.</span>
            ) : rec.text ? (
              <>
                <span className="serif" style={{ fontSize: 17, fontStyle: "italic" }}>
                  {rec.text}
                </span>
                {intervention && (
                  <span className="small muted" style={{ display: "block" }}>
                    Target {formatTargetDisplay(intervention.target_display)} · actual {formatTargetDisplay(intervention.actual_display)} ·{" "}
                    {intervention.observation_status === "missing" ? "no compliance data" : `followed ${Math.round((intervention.compliance_degree ?? 0) * 100)}%`}
                  </span>
                )}
              </>
            ) : (
              "No recommendation stored for this day."
            )}
          </dd>
        </div>
        <div>
          <dt>Safety</dt>
          <dd>{status.safety.active ? `${status.safety.highest_severity} · ${status.safety.flag_types.map(flagTypeLabel).join(", ")}` : "No active safety flag"}</dd>
        </div>
        <div>
          <dt>Model components</dt>
          <dd className="small muted">
            The XGBoost and state-engine estimates behind this fused value are stored for this day (circadian_labels) but not returned by the
            current API.
          </dd>
        </div>
      </dl>
    </section>
  );
}

/* ---------------- 8.7 / 8.8 ---------------- */

function RecommendationHistory({
  dates,
  allDates,
  statuses,
  interventionByDate,
  selectedDate,
  onSelect,
}: {
  dates: string[];
  allDates: string[];
  statuses: Record<string, StatusResponse>;
  interventionByDate: Record<string, InterventionHistoryEntry>;
  selectedDate: string;
  onSelect: (date: string) => void;
}) {
  const logged = dates.filter((d) => interventionByDate[d]);
  const followed = logged.filter((d) => interventionByDate[d].compliance_binary === true).length;
  const observed = logged.filter((d) => interventionByDate[d].observation_status === "observed").length;
  const latestEffect = [...dates].reverse().map((d) => interventionByDate[d]).find((e) => e && e.effect_estimate !== null);

  return (
    <>
      <p style={{ fontSize: 14, marginBottom: 12 }}>
        <strong>{logged.length}</strong> recommendations logged · followed on <strong>{followed}</strong> of <strong>{observed}</strong> observed days
        {latestEffect && latestEffect.effect_estimate !== null && (
          <>
            {" "}
            · latest {MEASUREMENT_PHASE_LABELS[latestEffect.measurement_phase ?? 1]?.toLowerCase() ?? "observed change"}:{" "}
            <strong>
              {Math.abs(Math.round(latestEffect.effect_estimate))} min {latestEffect.effect_estimate < 0 ? "earlier" : "later"}
            </strong>
          </>
        )}
      </p>
      <div style={{ overflowX: "auto" }}>
        <table className="record-table">
          <thead>
            <tr>
              <th>Day</th>
              <th>Recommendation</th>
              <th>Target</th>
              <th>Ranked #1 that day</th>
              <th>Actual</th>
              <th>Followed</th>
            </tr>
          </thead>
          <tbody>
            {dates.map((d) => {
              const st = statuses[d];
              const iv = interventionByDate[d];
              const top = st?.contributors.find((c) => c.rank === 1);
              return (
                <tr key={d} className={d === selectedDate ? "is-selected" : undefined} onClick={() => onSelect(d)} style={{ cursor: "pointer" }}>
                  <td data-label="Day">
                    {allDates.indexOf(d) + 1} <span className="small muted">{formatDateLong(d)}</span>
                  </td>
                  <td data-label="Recommendation">{st ? (st.recommendation.suppressed ? "Suppressed (safety)" : st.recommendation.text ?? "—") : "…"}</td>
                  <td data-label="Target">{formatTargetDisplay(iv?.target_display ?? st?.recommendation.target_display ?? null)}</td>
                  <td data-label="Ranked #1">{top ? contributorLabel(top.signal) : st ? "—" : "…"}</td>
                  <td data-label="Actual">{formatTargetDisplay(iv?.actual_display ?? null)}</td>
                  <td data-label="Followed">
                    {!iv ? (
                      "—"
                    ) : iv.observation_status === "missing" ? (
                      <span className="badge badge--neutral">No data</span>
                    ) : iv.compliance_binary ? (
                      <span className="badge badge--good">Yes · {Math.round((iv.compliance_degree ?? 0) * 100)}%</span>
                    ) : (
                      <span className="badge badge--moderate">No · {Math.round((iv.compliance_degree ?? 0) * 100)}%</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="small muted" style={{ marginTop: 10, fontStyle: "italic" }}>
        &ldquo;Followed&rdquo; is compliance measured from the behavior logged that day against the day&apos;s target. Effect estimates are observational
        associations, not proven effects. {CAUSAL_CAVEAT}
      </p>
    </>
  );
}

function Limitations() {
  return (
    <details className="atlas-section journey-limits">
      <summary className="section-label" style={{ cursor: "pointer" }}>
        Data contract notes · what the current API does not return
      </summary>
      <ul className="small muted">
        <li>Daily XGBoost and state engine DLMO estimates (stored in circadian_labels; the history and status endpoints return only the fused value).</li>
        <li>Per-day adapted state (the schema keeps only the latest adapted value on participant_profiles).</li>
        <li>Wake time, light start, screen end time, caffeine time and amount, exercise duration (stored in daily_observations; not in the behavior response).</li>
        <li>Supporting nudges for past dates (only the current recommendation endpoint returns nudges; the schema logs only the primary per day).</li>
        <li>Personalization phase and the stored intervention effect-estimate details beyond the per-log effect value.</li>
      </ul>
    </details>
  );
}
