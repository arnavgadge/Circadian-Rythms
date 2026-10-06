"""CircadianIQ XGBoost DLMO training + validation pipeline (Phase 5).

Trains an XGBoost model that predicts the target day's ``current_DLMO``
from the Phase 4 68-feature, six-day window vector. See
``docs/model_training_and_validation.md`` for the full design writeup.

Entry points:

- :func:`app.models.training.run_training_pipeline` -- data prep ->
  participant split -> grouped CV -> final fit -> held-out test ->
  stratified reporting, all in one call.
- :func:`app.models.training.persist_training_run` -- saves versioned
  model artifacts and logs a ``training_runs`` database row.
- :func:`app.models.diagnostics.build_diagnostics_plots` -- the 8
  required diagnostic plots.
- CLI: ``python -m app.scripts.train_model``.

Not to be confused with the top-level ``models/`` directory, which
stores the serialized artifacts this package produces.
"""
