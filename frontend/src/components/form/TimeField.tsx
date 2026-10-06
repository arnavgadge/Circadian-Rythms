interface TimeFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}

/** A native time picker (never freeform text) for HH:MM clock-time
 * inputs, matching the daily-entry/onboarding requirement to prefer
 * time pickers over arbitrary text. */
export function TimeField({ id, label, value, onChange }: TimeFieldProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <label htmlFor={id} style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
        {label}
      </label>
      <input
        id={id}
        type="time"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        style={{ padding: "8px 10px", borderRadius: "var(--radius-sm)", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-text)" }}
      />
    </div>
  );
}
