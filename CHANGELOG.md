# Changelog

All notable changes to CircadianIQ are recorded here.

## [1.0.0-research-demo] - 2026-09-09

First frozen release. Phase 18 packaging work: version freeze
(`release/version_manifest.json`), one-command reproduction
(`app/scripts/reproduce_release.py`), deterministic demo scenarios
(`app/scripts/seed_demo_scenarios.py`), release checksums
(`scripts/generate_checksums.py` -> `release/checksums.sha256`),
pinned dependency lockfile (`requirements-lock.txt`), and final
documentation (developer/research handoff, quickstart, release notes,
this changelog). No application code was modified during Phase 18.
See `release/version_manifest.json` for the authoritative Phase 18
release status.

### History

- **Phase 1** — Project foundation.
- **Phase 2** — Database layer (SQLAlchemy models, Alembic migrations).
- **Phase 3** — Synthetic participant/population data generation.
- **Phase 4** — Feature engineering pipeline.
- **Phase 5** — XGBoost DLMO model training and validation.
- **Phase 6** — Circadian state-model estimator.
- **Phase 7** — DLMO fusion (ML + state model).
- **Phase 8** — Alignment scoring engine.
- **Phase 9** — Contributor identification and ranking.
- **Phase 10** — Recommendation engine.
- **Phase 11** — Daily inference pipeline orchestration.
- **Phase 12** — Intervention effectiveness evaluation.
- **Phase 13** — Personalization (per-participant effect models, targeting).
- **Phase 14** — Safety and confidence layer.
- **Phase 15** — API layer (FastAPI).
- **Phase 16** — Dashboard UI (React/TypeScript).
- **Phase 17** — System-wide adversarial audit — CONDITIONAL PASS; 6
  real defects found and fixed with regression tests; 3 non-critical
  limitations documented.
- **Phase 18** — Version freeze, reproducibility packaging, final
  documentation, demo scenarios, research/paper drafts — release
  `v1.0.0-research-demo`.
