export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="loading">
      <span className="visually-hidden">{label}</span>
      <span className="loading__orbit" aria-hidden="true" />
      <span aria-hidden="true">{label}</span>
    </div>
  );
}

/** Placeholder lines while a secondary section loads. */
export function SkeletonLines({ lines = 3 }: { lines?: number }) {
  return (
    <div aria-hidden="true" style={{ display: "flex", flexDirection: "column", gap: 10, padding: "6px 0" }}>
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton-line" style={{ width: `${92 - i * 14}%` }} />
      ))}
    </div>
  );
}
