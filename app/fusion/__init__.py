"""CircadianIQ DLMO fusion layer (Phase 7).

Combines the Phase 5 XGBoost estimate and the Phase 6 state-engine
estimate into one authoritative fused daily DLMO, via the locked
four-layer Q26 model: base weights from data quality, a disagreement
adjustment, a biological continuity constraint, and a confidence
penalty. See ``docs/dlmo_fusion.md`` for the full design writeup.

This is an interpretable state-and-model fusion mechanism -- not a
Kalman filter, and not a claim that fusion improves real-world DLMO
accuracy (see the "Scientific limitations" section of that document).

Entry point: :func:`app.fusion.fuse.fuse`.
"""
