import { Icon } from "../atlas/Icon";
import { addDaysIso, formatDateLong, todayIso } from "../../utils/time";

/**
 * Calendar control: previous day / date picker / next day.
 * The date is shown in the atlas format ("15 Feb 2026") regardless of
 * browser locale; a native date input sits invisibly over it, so
 * clicking or keyboard-focusing it still uses the platform picker.
 * Purely a selector -- the parent decides which existing endpoint to
 * query for the chosen date. Never allows selecting a future date.
 */
export function DateNavigator({
  value,
  onChange,
  label = "Date",
  id = "date-nav",
}: {
  value: string;
  onChange: (date: string) => void;
  label?: string;
  id?: string;
}) {
  const today = todayIso();
  const atToday = value >= today;

  return (
    <div className="date-nav">
      <span className="date-nav__field">
        <Icon name="calendar" size={16} />
        <span className="date-nav__text" aria-hidden="true">
          {formatDateLong(value)}
        </span>
        <input
          id={id}
          className="date-nav__native"
          type="date"
          aria-label={label}
          value={value}
          max={today}
          onClick={(e) => {
            try {
              e.currentTarget.showPicker?.();
            } catch {
              // showPicker is unavailable in some browsers/contexts; the input still works by keyboard.
            }
          }}
          onChange={(e) => {
            if (e.target.value) onChange(e.target.value);
          }}
        />
      </span>
      <button type="button" className="icon-button" aria-label="Previous day" onClick={() => onChange(addDaysIso(value, -1))}>
        <Icon name="chevron-left" size={16} />
      </button>
      <button type="button" className="icon-button" aria-label="Next day" disabled={atToday} onClick={() => onChange(addDaysIso(value, 1))}>
        <Icon name="chevron-right" size={16} />
      </button>
    </div>
  );
}
