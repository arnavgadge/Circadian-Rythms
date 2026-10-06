"""CircadianIQ state engine (Phase 6): the three-layer circadian phase model.

    intrinsic DLMO -> adapted DLMO -> current DLMO

This is the single authoritative implementation of the state
transition and the behavioral-effect model that drives it -- shared by
the Phase 3 synthetic generator (via
``app.synthetic.dlmo_state``'s backward-compatible translation layer)
and available for future production inference. It is deliberately
independent of the Phase 5 XGBoost model: no import of trained models
or ML code appears anywhere in this package. See
``docs/state_engine.md`` for the full design writeup.

Entry points:

- :func:`app.state.engine.initialize_state` / ``initialize_state_stochastic``
- :func:`app.state.engine.step` (deterministic) / ``step_stochastic``
  (explicit randomness)
- :func:`app.state.replay.replay_trajectory` -- reproduce a full
  participant trajectory from ordered daily behavior inputs.
- :mod:`app.state.behavioral_effect` -- the shared light/screen/meal/
  exercise/caffeine effect model.
- :mod:`app.state.sanity` -- the 10 automated state sanity checks.
"""
