"""CircadianIQ synthetic population and 30-day longitudinal data generator.

See ``docs/synthetic_data_generation.md`` for the full design writeup
(participant generation, chronotype/MEQ/MSFsc generation, the seven
behavioral personalities, the stateful DLMO model, interaction
effects, and the source-backed vs. synthetic assumption boundary).

Entry points:

- :func:`app.synthetic.simulator.generate_synthetic_dataset` -- runs
  the full population + 30-day simulation, in memory.
- :func:`app.synthetic.validation.run_quality_checks` -- validates a
  generated dataset.
- :func:`app.synthetic.diagnostics.build_diagnostics_report` -- writes
  distribution plots/summary.
- :func:`app.synthetic.export.export_dataset` -- writes Parquet/JSON
  derived artifacts.
- :func:`app.synthetic.db_writer.write_dataset_to_db` -- writes the
  dataset into the Phase 2 relational schema (the authoritative store).
- CLI: ``python -m app.scripts.generate_synthetic_data``.
"""
