import { ApiError } from "../api/client";
import { friendlyErrorMessage } from "../utils/errors";
import { Icon } from "./atlas/Icon";

/** A single, consistent error presentation -- never a raw stack trace,
 * SQL error, or backend exception detail (only the API's own safe
 * `message`, itself already sanitized by Phase 15). */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const isApiError = error instanceof ApiError;
  const message = friendlyErrorMessage(error);

  return (
    <div className="notice notice--alert" role="alert">
      <span style={{ color: "var(--rust)", display: "inline-flex", paddingTop: 2 }}>
        <Icon name="info" size={20} />
      </span>
      <div style={{ flex: 1 }}>
        <p style={{ fontWeight: 600 }}>{message}</p>
        {isApiError && error.correlationId && <p className="small muted" style={{ marginTop: 4 }}>Reference: {error.correlationId}</p>}
        {onRetry && (
          <button type="button" className="button button--secondary button--small" style={{ marginTop: 10 }} onClick={onRetry}>
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * A quieter, non-alerting notice for a *secondary* section that
 * couldn't load (e.g. the day's observations under the main estimate).
 * The failure is still shown -- never silently swallowed -- but it
 * doesn't interrupt the page the way a primary-load ErrorState does.
 */
export function InlineNotice({ error, label, onRetry }: { error: unknown; label: string; onRetry?: () => void }) {
  return (
    <div className="notice">
      <span style={{ color: "var(--brown)", display: "inline-flex", paddingTop: 1 }}>
        <Icon name="info" size={18} />
      </span>
      <div style={{ flex: 1 }}>
        <p>
          {label} <span className="muted">{friendlyErrorMessage(error)}</span>
        </p>
        {onRetry && (
          <button type="button" className="button button--quiet button--small" style={{ paddingLeft: 0, marginTop: 4 }} onClick={onRetry}>
            <Icon name="refresh" size={14} /> Retry
          </button>
        )}
      </div>
    </div>
  );
}
