interface NumberFieldProps {
  id: string;
  label: string;
  value: number | "";
  min?: number;
  max?: number;
  onChange: (value: number | "") => void;
}

export function NumberField({ id, label, value, min, max, onChange }: NumberFieldProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <label htmlFor={id} style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
        {label}
      </label>
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(event.target.value === "" ? "" : Number(event.target.value))}
        style={{ padding: "8px 10px", borderRadius: "var(--radius-sm)", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-text)" }}
      />
    </div>
  );
}
