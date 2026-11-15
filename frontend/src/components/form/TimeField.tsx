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
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} className="input" type="time" value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}
