import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAction, useFetch } from "../hooks/useApi";
import { ErrorState } from "../components/ErrorState";
import { InterventionProgress } from "../components/InterventionProgress";
import { LoadingState } from "../components/LoadingState";
import { NumberField } from "../components/form/NumberField";
import { TimeField } from "../components/form/TimeField";
import { Icon } from "../components/atlas/Icon";
import { iconForSignal } from "../components/atlas/signals";
import { PageHeader } from "../components/layout/PageHeader";
import { CAUSAL_CAVEAT } from "../utils/messages";
import { MEASUREMENT_PHASE_LABELS, interventionTypeLabel } from "../utils/terminology";
import { formatDateLong, formatTargetDisplay } from "../utils/time";
import type { InterventionHistoryEntry, OutcomeSubmissionResponse } from "../api/types";

const CLOCK_VALUE = /^\d{1,2}:\d{2}$/;

/**
 * Interventions: the current behavioral focus and every logged
 * intervention day, read from `GET /interventions`. Each record can
 * receive an outcome through the existing
 * `POST /interventions/{id}/outcome` endpoint (exact request payload:
 * observation_date + actual_value_time | actual_value_numeric +
 * observed). Compliance and effect estimates are always the API's own
 * values; effect estimates are observational, never causal.
 */
export function Interventions({ participantId }: { participantId: number }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const history = useFetch(() => api.getInterventionHistory(participantId, { limit: 90 }), [participantId, refreshKey]);
  const entries = history.data?.entries ?? [];

  const currentType = entries[0]?.intervention_type ?? null;
  const current = currentType ? entries.filter((e) => e.intervention_type === currentType) : [];
  const firstLogged = current.length ? current[current.length - 1].log_date : null;
  const latest = current[0] ?? null;

  return (
    <div>
      <PageHeader title="Interventions" subtitle="Your current behavioral focus and how each logged day went." />

      {history.loading && !history.data ? (
        <LoadingState label="Loading your interventions…" />
      ) : history.error ? (
        <ErrorState error={history.error} onRetry={history.refetch} />
      ) : entries.length === 0 ? (
        <div className="empty-state" style={{ paddingTop: 0 }}>
          <span className="empty-state__title">No interventions yet</span>
          <p>An intervention is logged each time a daily estimate selects a primary focus for you.</p>
          <Link to={`/dashboard/${participantId}`} className="button button--primary button--small" style={{ marginTop: 8 }}>
            Go to dashboard
          </Link>
        </div>
      ) : (
        <>
          <div className="ruled-row ruled-row--focus" style={{ borderTop: "none" }}>
            <section aria-labelledby="current-heading" style={{ paddingTop: 0 }}>
              <div className="section-label" id="current-heading">
                Current intervention
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                <span style={{ color: "var(--burnt)", display: "inline-flex" }}>
                  <Icon name={iconForSignal(currentType)} size={34} strokeWidth={1.3} />
                </span>
                <div>
                  <h2 className="serif" style={{ fontSize: 30, fontStyle: "italic", lineHeight: 1.1 }}>
                    {interventionTypeLabel(currentType)}
                  </h2>
                  <p className="small muted">{latest?.intervention_code}</p>
                </div>
              </div>
              <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 16, margin: "20px 0 0" }}>
                <Fact label="Latest target" value={displayValue(latest?.target_display ?? null)} />
                <Fact label="First logged" value={formatDateLong(firstLogged)} />
                <Fact label="Most recent day" value={formatDateLong(latest?.log_date ?? null)} />
                <Fact label="Logged days" value={String(current.length)} />
              </dl>
            </section>
            <div style={{ paddingTop: 0 }}>
              <InterventionProgress entries={entries} />
            </div>
          </div>

          <section className="atlas-section" style={{ marginTop: 8 }} aria-labelledby="records-heading">
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "baseline" }}>
              <div className="section-label" id="records-heading">
                Intervention records
              </div>
              <span className="small muted">{entries.length} most recent</span>
            </div>
            <RecordsTable participantId={participantId} entries={entries} onSaved={() => setRefreshKey((k) => k + 1)} />
            <p className="small muted" style={{ marginTop: 14, fontStyle: "italic" }}>
              Effect estimates are observational associations within CircadianIQ&apos;s model, not proven effects. {CAUSAL_CAVEAT}
            </p>
          </section>
        </>
      )}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="small muted">{label}</dt>
      <dd className="serif" style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
        {value}
      </dd>
    </div>
  );
}

function displayValue(value: string | null): string {
  return formatTargetDisplay(value);
}

function RecordsTable({ participantId, entries, onSaved }: { participantId: number; entries: InterventionHistoryEntry[]; onSaved: () => void }) {
  const [openId, setOpenId] = useState<number | null>(null);

  return (
    <table className="record-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Intervention</th>
          <th>Target</th>
          <th>Actual</th>
          <th>Followed</th>
          <th>Effect estimate</th>
          <th>
            <span className="visually-hidden">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {entries.map((entry) => (
          <RecordRow
            key={entry.intervention_log_id}
            participantId={participantId}
            entry={entry}
            open={openId === entry.intervention_log_id}
            onToggle={() => setOpenId((id) => (id === entry.intervention_log_id ? null : entry.intervention_log_id))}
            onSaved={onSaved}
          />
        ))}
      </tbody>
    </table>
  );
}

function RecordRow({
  participantId,
  entry,
  open,
  onToggle,
  onSaved,
}: {
  participantId: number;
  entry: InterventionHistoryEntry;
  open: boolean;
  onToggle: () => void;
  onSaved: () => void;
}) {
  const followed =
    entry.observation_status === "missing" ? (
      <span className="badge badge--neutral">No data</span>
    ) : entry.compliance_binary ? (
      <span className="badge badge--good">Followed</span>
    ) : (
      <span className="badge badge--moderate">Not followed</span>
    );

  return (
    <>
      <tr>
        <td data-label="Date">{formatDateLong(entry.log_date)}</td>
        <td data-label="Intervention">
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name={iconForSignal(entry.intervention_type)} size={15} />
            {interventionTypeLabel(entry.intervention_type)}
          </span>
        </td>
        <td data-label="Target">{displayValue(entry.target_display)}</td>
        <td data-label="Actual">{displayValue(entry.actual_display)}</td>
        <td data-label="Followed">
          {followed}
          {entry.compliance_degree !== null && <span className="small muted"> {Math.round(entry.compliance_degree * 100)}%</span>}
        </td>
        <td data-label="Effect">
          {entry.effect_estimate !== null ? (
            <span title={MEASUREMENT_PHASE_LABELS[entry.measurement_phase ?? 1]}>
              {Math.abs(Math.round(entry.effect_estimate))} min {entry.effect_estimate < 0 ? "earlier" : "later"}
              <span className="small muted" style={{ display: "block" }}>
                {MEASUREMENT_PHASE_LABELS[entry.measurement_phase ?? 1] ?? "Observed change"}
              </span>
            </span>
          ) : (
            <span className="muted">—</span>
          )}
        </td>
        <td style={{ textAlign: "right" }}>
          <button type="button" className="button button--quiet button--small" aria-expanded={open} onClick={onToggle}>
            {entry.observation_status === "missing" ? "Record outcome" : "Update outcome"}
          </button>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={7} style={{ borderBottom: "none", paddingTop: 0 }}>
            <OutcomeForm participantId={participantId} entry={entry} onSaved={onSaved} />
          </td>
        </tr>
      )}
    </>
  );
}

function OutcomeForm({ participantId, entry, onSaved }: { participantId: number; entry: InterventionHistoryEntry; onSaved: () => void }) {
  // target_display is "HH:MM" for clock-time interventions and a plain
  // number otherwise (see app/api/services/intervention_service.py);
  // the matching input is offered. The backend re-validates the kind.
  const isClock = entry.target_display ? CLOCK_VALUE.test(entry.target_display.trim()) : true;
  const [timeValue, setTimeValue] = useState("");
  const [numericValue, setNumericValue] = useState<number | "">("");
  const [result, setResult] = useState<OutcomeSubmissionResponse | null>(null);

  const submit = useAction((observed: boolean) =>
    api.submitInterventionOutcome(participantId, entry.intervention_log_id, {
      observation_date: entry.log_date,
      actual_value_time: observed && isClock && timeValue ? timeValue : null,
      actual_value_numeric: observed && !isClock && numericValue !== "" ? numericValue : null,
      observed,
    }),
  );

  async function handle(observed: boolean) {
    setResult(null);
    try {
      const response = await submit.run(observed);
      setResult(response);
      onSaved();
    } catch {
      // submit.error is rendered below.
    }
  }

  const hasValue = isClock ? timeValue !== "" : numericValue !== "";
  const idBase = `outcome-${entry.intervention_log_id}`;

  return (
    <form
      className="outcome-form"
      onSubmit={(e) => {
        e.preventDefault();
        void handle(true);
      }}
      aria-label={`Outcome for ${formatDateLong(entry.log_date)}`}
    >
      <p className="small" style={{ width: "100%" }}>
        What did you actually do on {formatDateLong(entry.log_date)}?{entry.target_display ? ` Target was ${displayValue(entry.target_display)}.` : ""}
      </p>
      {isClock ? (
        <TimeField id={`${idBase}-time`} label="Actual time" value={timeValue} onChange={setTimeValue} />
      ) : (
        <NumberField id={`${idBase}-num`} label="Actual amount" min={-1000} max={1000} value={numericValue} onChange={setNumericValue} />
      )}
      <button type="submit" className="button button--primary button--small" disabled={!hasValue || submit.loading}>
        {submit.loading ? "Saving…" : "Save outcome"}
      </button>
      <button type="button" className="button button--secondary button--small" disabled={submit.loading} onClick={() => void handle(false)}>
        No data for this day
      </button>
      {result && (
        <p className="form-message form-message--success" role="status" style={{ width: "100%" }}>
          <Icon name="check" size={15} />
          {result.applied
            ? `Outcome saved${result.compliance_binary === null ? "." : result.compliance_binary ? " — recorded as followed." : " — recorded as not followed."}`
            : "Saved as no data for this day."}
        </p>
      )}
      {submit.error && (
        <div style={{ width: "100%" }}>
          <ErrorState error={submit.error} />
        </div>
      )}
    </form>
  );
}
