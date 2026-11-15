import type { IconName } from "./Icon";

/** One icon per behavioral signal / intervention type, used identically
 * on the dashboard, log form, history heatmap and intervention views. */
export const SIGNAL_ICON: Record<string, IconName> = {
  sleep: "bed",
  sleep_consistency: "bed",
  light: "sun",
  morning_light: "sun",
  screen: "monitor",
  evening_screen: "monitor",
  meal: "cutlery",
  meal_timing: "cutlery",
  exercise: "activity",
  caffeine: "cup",
  social_jetlag: "jetlag",
};

export function iconForSignal(signal: string | null | undefined): IconName {
  return (signal && SIGNAL_ICON[signal]) || "dashboard";
}
