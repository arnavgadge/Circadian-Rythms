# CircadianIQ User-Facing UI/Dashboard (Phase 16)

## 1. UI architecture

```
BROWSER (React + TypeScript SPA, Vite build)
  -> centralized typed API client (frontend/src/api/client.ts)
    -> Phase 15 REST API (/api/v1/...) over HTTP
      -> everything from Phase 4-14 (unchanged)
```

The frontend is a standalone Vite/React application under `frontend/`.
It contains **no domain, ML, statistical, or safety logic**: every
number, label, and piece of copy shown to a participant is either (a)
returned verbatim by the Phase 15 API, or (b) a fixed, pre-approved
string looked up from a small terminology/messages table
(`src/utils/terminology.ts`, `src/utils/messages.ts`) keyed off an
API-provided enum (e.g. `confidence.label`, `safety.highest_severity`).
The UI never imports XGBoost, never touches SQL, and never computes
DLMO, alignment, contributor ranking, recommendations, personalization
state, or safety flags itself.

## 2. Component hierarchy

```
App
├─ Header (nav, "Research mode" toggle)
└─ Routes
   ├─ ParticipantPicker            (/)
   ├─ Onboarding                   (/onboarding)
   ├─ Dashboard                    (/dashboard/:participantId)
   │  ├─ BiologicalClockCard
   │  │  └─ ClockVisualization (SVG)
   │  ├─ SafetyBanner (conditional)
   │  ├─ AlignmentScore
   │  ├─ AlignmentBreakdown
   │  ├─ RecommendationCard
   │  │  └─ NudgeCard (supporting, max 2)
   │  ├─ ContributorsList
   │  │  └─ ContributorCard
   │  ├─ InterventionProgress
   │  ├─ TrajectoryChart
   │  └─ DevPanel (conditional, "Research mode" only)
   └─ DailyEntry                   (/log/:participantId)
```

Shared primitives: `ConfidenceBadge`, `ErrorState`, `LoadingState`,
`form/TimeField`, `form/NumberField`.

## 3. API consumption

All network access goes through `src/api/client.ts` -- a single
`api` object with one typed method per Phase 15 endpoint, built on one
`request<T>()` helper. No component ever calls `fetch` directly (the
one exception is Vitest test files, which stub `global.fetch` to
avoid hitting a real server). `src/api/types.ts` hand-mirrors every
Pydantic response model 1:1; the UI only ever reads fields that exist
on those types, so a field the backend doesn't expose cannot silently
appear in the UI.

## 4. State management

No Redux/Zustand/react-query. Two small custom hooks
(`src/hooks/useApi.ts`) cover every case the dashboard needs:

- `useFetch(fetcher, deps)` -- GET-style reads; tracks
  `loading`/`error`/`data` and exposes `refetch`.
- `useAction(action)` -- POST-style mutations (run inference, submit
  onboarding, save a daily entry); tracks `loading`/`error` and
  exposes `run()`.

`Dashboard` holds one `refreshKey` piece of local state; incrementing
it after a successful `POST /inference` re-runs every `useFetch` call
on the page. This is the only cross-component "state sharing" in the
app, and it lives in a single page component, not a global store.

## 5. Dashboard structure

Single scrolling page (`.dashboard-grid`, defined in
`styles/theme.css`): 2-column CSS grid on desktop, collapses to 1
column under 760px. Full-width elements (clock card, safety banner,
recommendation, trajectory chart) span both columns via
`grid-column: 1 / -1`. Order, top to bottom: biological clock ->
safety banner (if active) -> alignment score + breakdown ->
recommendation -> contributors -> intervention progress -> trajectory
chart -> optional dev panel.

## 6. Onboarding flow

Six linear steps (`welcome -> boundary -> meq -> mctq -> confirm ->
done`), a `<nav>` progress bar, back/continue buttons. Only collects
what `POST /participants` actually accepts:
`participant_code`, `meq_score` (0-100 slider), `msfsc_time` (a
single free-day sleep-midpoint time picker). See "Limitations" below
for why this isn't a full item-level MEQ/MCTQ questionnaire. On
success, `Onboarding` hands the new `participant_id` back to its
route wrapper, which navigates to `/log/:participantId` so the
participant's first action is logging real behavioral data (the
system has no prediction until daily inference has history to work
with -- this is surfaced via the API's `note` field, not invented
copy).

## 7. Chart behavior

`TrajectoryChart` renders `circadian/history` entries as a hand-rolled
SVG line, with 7/30/90-day range buttons and a metric tab
(clock time / alignment score / confidence score). For the "clock
time" metric, raw hour-of-day values are passed through
`unwrapHourSeries` (`src/utils/time.ts`) before plotting -- a
faithful TypeScript port of the circular-unwrap technique used by the
Python `circular_diff_hours`/unwrap helpers established in earlier
phases -- so a trajectory crossing midnight (e.g. 23:50 -> 00:10)
renders as one continuous line instead of a vertical drop to zero.
The unwrapped values are for rendering only; nothing recomputed here
is persisted or fed back into any calculation.

## 8. Safety states

Driven entirely by `status.safety` / `recommendation.suppressed` /
`recommendation.safety_message` from the API:

- **Inactive** (`safety.active === false`): `SafetyBanner` renders
  `null`. No safety UI is shown.
- **Moderate**: a neutral "Pattern note" banner using the API's
  message, `role="status"`.
- **High**: `RecommendationCard` renders `null` entirely (the
  suppressed recommendation is never shown, dimmed, or partially
  shown), and `SafetyBanner` renders the API's `safety_message` with
  `role="alert"`.

## 9. Confidence states

`ConfidenceBadge` + `qualifier_message` cover four states, all driven
by `confidence.label` / `prediction_available`:

- **high**: badge only, no qualifier text.
- **moderate**: badge + the API's moderate qualifier sentence.
- **low**: badge + qualifier sentence + `~` prefix on the clock value
  (never a bare unqualified number).
- **no_prediction**: `BiologicalClockCard` shows "Not enough data for
  today's estimate" and never falls back to a stale or fabricated
  clock value -- verified by
  `BiologicalClockCard.test.tsx`'s "never fabricates a clock value"
  test.

## 10. Accessibility

- Semantic landmarks (`<header>`, `<main>`, `<nav aria-label>`,
  `<section aria-labelledby>`).
- `AlignmentBreakdown` bars use `role="progressbar"` +
  `aria-valuenow/min/max` + a visible numeric label (never
  color-only).
- `ClockVisualization` is `role="img"` with a full text `aria-label`
  describing every plotted value, so the same information is
  available without seeing the SVG.
- `SafetyBanner`'s high-severity state is `role="alert"`
  (auto-announced); moderate is `role="status"`.
- All form fields (`TimeField`, `NumberField`, onboarding inputs) have
  a real associated `<label>`; nothing is icon/color-only.
- Covered by `src/components/__tests__/accessibility.test.tsx` plus
  role-based queries throughout the rest of the suite (tests query by
  role/label, not CSS selectors, which incidentally enforces this).

## 11. Responsive design

`.dashboard-grid` and form layouts use CSS grid/flexbox with a single
760px breakpoint (`styles/theme.css`) collapsing 2 columns to 1;
everything else (cards, buttons, the SVG clock) is defined in
relative units and scales down naturally. No fixed-width layouts
outside the onboarding/entry cards, which are intentionally
constrained (`max-width`) for readability rather than to fit a
specific viewport.

## 12. Terminology

Fixed lookups only, no dynamic NLG:

| Concept | Approved | Avoided |
|---|---|---|
| Biological clock estimate | "Estimated Biological Clock" | "Clinical DLMO" |
| Contributors | "Top contributors" (non-causal phrasing, "modeled influence") | "Causes" / "caused" |
| Recommendation | "This week's primary focus" / "Supporting nudges" | Three equal-weight suggestions |
| Personalization | phase labels from `personalizationLabel()` | "Thompson sampling", "posterior" |
| Safety (moderate) | "Pattern note" | Alarming language |
| Safety (high) | API's fixed `safety_message` | Any UI-authored substitute |
| No prediction | "Not enough data for today's estimate" | A stale/fabricated value |

Every one of these strings is centralized in `utils/terminology.ts`
/ `utils/messages.ts` -- there is exactly one place to check or update
approved copy.

## 13. Limitations (explicitly out of scope for Phase 16)

- **Onboarding is not a full item-level MEQ/MCTQ questionnaire.**
  Phase 15's `POST /participants` only accepts an aggregate
  `meq_score` and a single `msfsc_time`; no phase has defined a
  structured item-level question schema over the API. Building one
  client-side would mean inventing MEQ/MCTQ scoring logic in the UI,
  which is explicitly forbidden. The onboarding flow collects exactly
  the fields the backend accepts and no more.
- **Recommendations carry no "why" rationale field.** The API does not
  return an explanation string beyond `text`/`target_display`/
  `expected_improvement_*`; the UI does not synthesize one.
- **`InterventionProgress` shows no before/after DLMO or alignment
  values.** `GET /interventions` does not expose those; the card only
  aggregates fields already present on `InterventionHistoryEntry`
  (compliance over observed days, the latest `effect_estimate` if
  present) -- a presentational aggregation over already-fetched rows,
  not a new statistical computation.
- **There is no manual "did you follow this recommendation?"
  confirmation UI.** Compliance is derived automatically by Phase 12
  from logged behavior (via daily entry) compared against the
  recommendation target, not self-reported, so `POST
  /interventions/{id}/outcome` (exposed on the API client for
  completeness) has no corresponding UI action in this phase.
- **`DevPanel` ("Research mode") only surfaces fields the API already
  returns on `StatusResponse`/`CircadianHistoryEntry`** (e.g.
  `disagreement_regime`, `prediction_status`, raw component scores).
  It does not expose raw XGBoost outputs, internal state-estimator
  values, or a model/pipeline version, because Phase 15 does not
  return those over the API.

## Running the frontend

```
cd frontend
npm install
cp .env.example .env   # set VITE_API_BASE_URL if the API isn't on 127.0.0.1:8000
npm run dev             # http://127.0.0.1:5173
npm run build            # production build (tsc -b && vite build)
npm test                 # vitest run -- 49 tests across 16 files (component + integration/E2E)
```

The API (`uvicorn app.api.main:app --reload`, from the repo root) must
be running for the dashboard to load real data.
