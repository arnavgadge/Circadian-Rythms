"""CircadianIQ contributor ranking engine (Phase 9).

Ranks the five candidate behavioral signals (evening screen, morning
light, meal timing, social jetlag, exercise) by how much each is
estimated to be contributing to the participant's current
misalignment, combining a normalized recent phase-shift effect (60%,
reusing Phase 6's authoritative behavioral-effect model) with a Phase 8
alignment-component deficit (40%). Returns the top 3 (or fewer, if
fewer than three valid signals exist) plus a separate "today's
anomaly" comparison against the participant's own six-day pattern.

This engine identifies contributors *within CircadianIQ's modeled
system* -- never causes, proven causes, or medical causes -- and
selects no intervention (Phase 10). See
``docs/contributor_ranking.md`` for the full design writeup.

Entry point: :func:`app.contributors.engine.rank_contributors`.
"""
