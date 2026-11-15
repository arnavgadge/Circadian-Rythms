/**
 * Identity of the database-backed 30-day research demonstration
 * participant created by scripts/demo/seed_demo_participant.py.
 * The numeric id is only a locator: the page always confirms the
 * participant's real participant_code through GET /participants/{id}
 * before showing anything, and refuses to present any other record
 * as the demonstration.
 */
export const DEMO_PARTICIPANT_CODE = "DEMO-001";
export const DEMO_PARTICIPANT_ID: number = Number((import.meta.env.VITE_DEMO_PARTICIPANT_ID as string | undefined) ?? 9101);
export const DEMO_DAYS = 30;
/** The pipeline predicts day N from days N-6..N-1, so days 1-6 are warm-up. */
export const WARMUP_DAYS = 6;
export const SYNTHETIC_LABEL = "Synthetic research participant";

export function isDemoParticipantCode(code: string | null | undefined): boolean {
  return code === DEMO_PARTICIPANT_CODE;
}
