# CircadianIQ Application/API Layer (Phase 15)

## 1. Layered architecture

```
CLIENT -> API (FastAPI routes) -> APPLICATION SERVICES -> DOMAIN/INTELLIGENCE MODULES (Phases 4-14) -> REPOSITORIES -> DATABASE
```

Routes (`app/api/routers/`) only translate HTTP <-> a call into an
application service (`app/api/services/`) and return a typed Pydantic
response model. **No route contains biological, ML, recommendation, or
safety logic** -- every computation is delegated to the existing
Phase 4-14 modules; services only orchestrate and format. Repositories
(`app/api/repositories/`) are the only place that issues SQLAlchemy
queries.

## 2. Endpoint catalogue

All routes are versioned under `/api/v1`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Application/DB/model-artifact/config readiness |
| POST | `/participants` | Onboard a new participant |
| GET | `/participants/{id}` | Safe participant profile |
| GET | `/participants/{id}/status` | Current circadian status (read-only) |
| POST | `/participants/{id}/inference` | Run daily inference (computation + persistence) |
| GET | `/participants/{id}/circadian/history` | Historical circadian trajectory |
| GET | `/participants/{id}/behavior` | Recent behavioral observations |
| GET | `/participants/{id}/contributors/current` | Current top contributors |
| GET | `/participants/{id}/recommendation/current` | Current recommendation (safety-aware) |
| GET | `/participants/{id}/interventions` | Intervention history |
| POST | `/participants/{id}/interventions/{log_id}/outcome` | Record an observed outcome |
| GET | `/participants/{id}/safety` | Safety status |

Interactive OpenAPI documentation is available at `/docs` (and the raw
schema at `/openapi.json`) whenever the API is running.

## 3. Request/response contracts

Every endpoint has an explicit Pydantic request/response model
(`app/api/schemas/`) -- **raw SQLAlchemy ORM objects are never
returned**. `StatusResponse` is the richest contract (matches the
brief's example): `biological_clock`, `chronotype`, `alignment`,
`confidence`, `contributors`, `recommendation`, `safety`,
`boundary_note`. Every prediction-capable response carries
`boundary_note = "Estimated from behavioral patterns. Not a clinical measurement."`
imported directly from `app.safety.messages` (never duplicated).

## 4. Service layer

| Service | Responsibility |
|---|---|
| `ParticipantService` | Profile reads, onboarding |
| `StatusService` | Composes the current-status contract from persisted state only |
| `InferenceService` | Calls `run_daily_inference` then `SafetyEngine.evaluate` in sequence |
| `HistoryService` / `BehaviorService` | Read-only trajectory/behavior queries |
| `ContributorService` / `RecommendationService` | Read persisted Phase 9/10 results |
| `InterventionService` | History reads + outcome submission (via Phase 12's `evaluate_compliance`) |
| `SafetyService` | Read-only safety status |
| `HealthService` | Liveness/readiness checks |

## 5. Repository layer

`ParticipantRepository`, `CircadianRepository`, `BehaviorRepository`,
`InterventionRepository`, `SafetyRepository` -- each a thin wrapper
around the Phase 2 SQLAlchemy models, injected into services via
FastAPI's dependency system. No route or service issues a raw query
directly.

## 6. Inference boundary

`POST /inference` is the **only** endpoint that triggers computation.
It calls `app.pipeline.orchestrator.run_daily_inference(...)` --
**never reimplemented** -- which owns its own read/compute/write
transaction boundary exactly as Phase 11 designed it. `GET /status`
and every other GET endpoint are pure database reads and never call
the inference pipeline (verified directly:
`test_get_status_does_not_create_a_circadian_label`).

## 7. Safety boundary

Immediately after `run_daily_inference` returns, `InferenceService`
calls `app.safety.engine.SafetyEngine.evaluate(...)` with that same
result's `fusion_result`/`alignment_result`/primary recommendation --
composing two already-complete phases in sequence, not reimplementing
either. `GET /recommendation/current` and `GET /safety` read the
resulting persisted `recommendation_suppressed`/`safety_severity`
state; **the API never independently decides what is safe to show**.

## 8. Error handling

Centralized in `app/api/main.py`: every service raises a typed
`app.api.errors.ApplicationError` subclass
(`NotFoundError` -> 404, `ValidationFailedError` -> 400,
`ConflictError` -> 409, `DependencyUnavailableError` -> 503); pydantic
validation failures are FastAPI's own 422; anything unexpected is
caught by a catch-all handler that logs the full exception server-side
and returns a generic `internal_error` (500) to the client -- **no
stack trace or database detail is ever leaked**. Every error response
shares one shape (`ErrorResponse`): `error`, `message`, `detail`,
`correlation_id`.

## 9. Idempotency

`POST /inference` passes straight through to Phase 11's own
idempotency guarantee: a repeated call for the same participant/date
(without `force_rerun`) returns the existing persisted result
(`idempotent_short_circuit=True` in the response) rather than creating
a duplicate `circadian_labels` row -- verified directly
(`test_flow_2_idempotent_inference`).

## 10. Logging

Structured request logging (`app.api.middleware.CorrelationIdMiddleware`):
method, path, correlation ID, status code, duration for every request;
full exception logged server-side on failure. Never logs credentials,
environment secrets, or raw behavioral data.

## 11. Versioning

All routes live under `/api/v1`; there is no unversioned production
route. A future breaking change would be introduced as `/api/v2`
alongside the existing version, never as an in-place breaking edit to
`v1`'s contracts.

## 12. Prototype security limitations

**This prototype implements no authentication or authorization.**
Every endpoint is reachable by anyone who can reach the process. This
is an explicit, documented development-only assumption, not a claim of
production readiness:

- No auth token/session is required or validated anywhere.
- Endpoint design is participant-ID-scoped (`/participants/{id}/...`)
  specifically so an authenticated-user-scoping layer can be added
  later (e.g. a dependency that resolves the caller's own
  `participant_id` and rejects mismatched requests) without changing
  any route shape.
- No production rate limiting is implemented; the only safeguard
  against runaway repeated inference calls is Phase 11's own
  idempotency/persistence protection (a repeated call is cheap and
  produces no duplicate state, but nothing currently throttles request
  *volume* itself).
- `create_all_tables` runs automatically at startup only in
  non-production environments (`APIConfig.is_development`); a real
  deployment must manage schema exclusively through Alembic migrations.
- CORS, TLS termination, and secret management are all deployment
  concerns explicitly out of scope for this phase.

A future phase (or the eventual production deployment) must add real
authentication/authorization before this API is exposed beyond local
development.
