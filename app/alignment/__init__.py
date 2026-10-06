"""CircadianIQ alignment engine (Phase 8).

Converts the fused estimated DLMO (Phase 7's output) and the
participant's actual behavior into a personalized 0-100 alignment
score: ``final = 0.60 * phase_alignment + 0.40 * behavioral_alignment``.
A score of 100 means "aligned with *your own* estimated phase and
recent behavior" -- never "matches a universal healthy schedule". See
``docs/alignment_engine.md`` for the full design writeup.

Entry point: :func:`app.alignment.engine.compute_alignment`.
"""
