"""The Phase 14 safety + confidence layer.

Sits above the completed inference pipeline: confidence gating ->
persistent unusual-pattern detection -> safety decision -> safe output
contract. Never modifies the underlying DLMO prediction, only whether/
how it is shown. Entry point: ``app.safety.engine.SafetyEngine.evaluate``.
"""
