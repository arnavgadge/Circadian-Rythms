import { ApiError } from "../api/client";

const FRIENDLY_MESSAGE_BY_STATUS: Record<number, string> = {
  0: "CircadianIQ can't be reached right now. Check that the API is running.",
  404: "We couldn't find that participant or result.",
  400: "That request couldn't be completed with the current data.",
  409: "That action was already completed.",
  422: "Some of the information provided wasn't valid.",
  503: "CircadianIQ's inference service is temporarily unavailable. Please try again shortly.",
  500: "Something went wrong on our end. Please try again.",
};

/** A single, consistent error presentation -- never a raw stack trace,
 * SQL error, or backend exception detail (only the API's own safe
 * `message`, itself already sanitized by Phase 15). */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const isApiError = error instanceof ApiError;
  const message = isApiError ? FRIENDLY_MESSAGE_BY_STATUS[error.status] ?? error.message : "Something went wrong. Please try again.";

  return (
    <div className="card" role="alert" style={{ textAlign: "center" }}>
      <p style={{ fontWeight: 600 }}>{message}</p>
      {isApiError && error.correlationId && (
        <p style={{ fontSize: 12, color: "var(--color-text-faint)", marginTop: 6 }}>Reference: {error.correlationId}</p>
      )}
      {onRetry && (
        <button type="button" className="button button--secondary" style={{ marginTop: 14 }} onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
