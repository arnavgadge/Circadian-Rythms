"""String constants for the safety layer. Plain string constants (not
a Python ``Enum``) to match the convention already used throughout
``app.contributors``/``app.recommendations``/``app.effectiveness``;
confidence labels specifically reuse ``app.fusion.config.ConfidenceLabel``
directly rather than a parallel enum -- see ``app.safety.confidence_gate``.
"""

from __future__ import annotations

# --- Display precision (Layer 1: confidence gating) ---
NORMAL = "NORMAL"
NORMAL_WITH_QUALIFIER = "NORMAL_WITH_QUALIFIER"
APPROXIMATE = "APPROXIMATE"
NONE_ = "NONE"

# --- Flag types (Layer 2: persistent unusual-pattern detection) ---
PERSISTENT_LATE_PHASE = "persistent_late_phase"
PERSISTENT_EARLY_PHASE = "persistent_early_phase"
CONTINUOUS_DLMO_DRIFT = "continuous_dlmo_drift"
LOW_ALIGNMENT_DESPITE_COMPLIANCE = "low_alignment_despite_compliance"

FLAG_TYPES = (PERSISTENT_LATE_PHASE, PERSISTENT_EARLY_PHASE, CONTINUOUS_DLMO_DRIFT, LOW_ALIGNMENT_DESPITE_COMPLIANCE)

# --- Flag lifecycle ---
DETECTED = "DETECTED"
PERSISTING = "PERSISTING"
RESOLVED = "RESOLVED"

# --- Severity (locked: exactly two levels) ---
MODERATE = "MODERATE"
HIGH = "HIGH"

# --- Overall safe-output status ---
STATUS_OK = "OK"
STATUS_FLAGGED = "FLAGGED"
STATUS_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
