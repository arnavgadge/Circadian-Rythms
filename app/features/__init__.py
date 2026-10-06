"""CircadianIQ Version-1 feature engineering layer.

Transforms exactly six previous complete days of a participant's raw
behavioral history into the 68-feature vector defined by
``app.features.feature_manifest.MANIFEST``. See
``docs/feature_engineering.md`` for the full design writeup.

Entry points:

- :func:`app.features.builder.build_features` -- one participant, one
  target date -> one :class:`~app.features.builder.FeatureVector`.
- :func:`app.features.dataset.build_feature_dataset` -- many
  participants -> the full feature matrix + metadata + targets.
- :func:`app.features.validation.validate_feature_vector` -- the 15
  automated sanity checks.
- :func:`app.features.diagnostics.build_diagnostics_report` --
  per-feature statistics.
- CLI: ``python -m app.scripts.build_feature_dataset``.
"""
