export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" style={{ padding: "var(--space-6)", textAlign: "center", color: "var(--color-text-muted)" }}>
      <span className="visually-hidden">{label}</span>
      <div aria-hidden="true" style={{ display: "flex", justifyContent: "center", gap: 6, marginBottom: 10 }}>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "var(--color-accent)",
              opacity: 0.3 + i * 0.3,
            }}
          />
        ))}
      </div>
      <span aria-hidden="true">{label}</span>
    </div>
  );
}
