interface NumberFieldProps {
  id: string;
  label: string;
  value: number | "";
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
  onChange: (value: number | "") => void;
}

export function NumberField({ id, label, value, min, max, step, placeholder, onChange }: NumberFieldProps) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        className="input"
        type="number"
        inputMode="decimal"
        min={min}
        max={max}
        step={step}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value === "" ? "" : Number(event.target.value))}
      />
    </div>
  );
}
