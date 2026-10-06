"""Fixed, structured safety/output messages -- looked up by key, never
generated dynamically (no LLM, no string templating beyond the
already-established pattern from Phase 10's recommendation templates).
Every string a user could ever see from this layer lives here, in one
place, so ``docs/safety_and_confidence.md`` "Prohibited claims" can be
verified by inspection rather than by grepping the whole codebase.
"""

from __future__ import annotations

# --- Wellness/research boundary (always present on a prediction-capable output) ---
BOUNDARY_NOTE_SHORT = "Estimated from behavioral patterns. Not a clinical measurement."

BOUNDARY_NOTE_ONBOARDING = (
    "CircadianIQ estimates your circadian phase from behavioral patterns. "
    "It is not a medical device, does not perform laboratory measurements, "
    "and does not diagnose any condition."
)

# --- Confidence-qualifier messages (Layer 1) ---
QUALIFIER_MODERATE = "Estimated from partial data."
QUALIFIER_LOW = "Approximate — complete more data for better accuracy."
INSUFFICIENT_DATA_GUIDANCE = (
    "Not enough recent data to produce a reliable estimate. "
    "Log a few more days of morning light, evening screen use, and sleep timing to continue."
)

# --- Non-diagnostic disclaimer (always accompanies an active safety flag) ---
NON_DIAGNOSTIC_STATEMENT = (
    "This is a pattern observation, not a medical diagnosis. "
    "CircadianIQ does not diagnose sleep or circadian rhythm disorders."
)

# --- Per-flag-type messages (Layer 2) ---
MESSAGE_PERSISTENT_LATE_PHASE = (
    "Your estimated biological clock has been consistently late for several weeks. "
    "If this affects your daily functioning, speaking with a sleep specialist may be helpful."
)
MESSAGE_PERSISTENT_EARLY_PHASE = (
    "Your estimated biological clock is consistently early. "
    "If early waking or evening sleepiness affects you, a sleep specialist can help."
)
MESSAGE_CONTINUOUS_DLMO_DRIFT = (
    "Your estimated biological clock appears to be drifting consistently. "
    "If this pattern continues, a sleep specialist can help evaluate it."
)
MESSAGE_LOW_ALIGNMENT_DESPITE_COMPLIANCE = (
    "You've been following your recommendations consistently, but your alignment score remains low. "
    "This pattern may benefit from professional evaluation."
)

FLAG_MESSAGE_KEYS = {
    "persistent_late_phase": "MESSAGE_PERSISTENT_LATE_PHASE",
    "persistent_early_phase": "MESSAGE_PERSISTENT_EARLY_PHASE",
    "continuous_dlmo_drift": "MESSAGE_CONTINUOUS_DLMO_DRIFT",
    "low_alignment_despite_compliance": "MESSAGE_LOW_ALIGNMENT_DESPITE_COMPLIANCE",
}

FLAG_MESSAGES = {
    "persistent_late_phase": MESSAGE_PERSISTENT_LATE_PHASE,
    "persistent_early_phase": MESSAGE_PERSISTENT_EARLY_PHASE,
    "continuous_dlmo_drift": MESSAGE_CONTINUOUS_DLMO_DRIFT,
    "low_alignment_despite_compliance": MESSAGE_LOW_ALIGNMENT_DESPITE_COMPLIANCE,
}

# --- High-severity recommendation-suppression message ---
HIGH_SEVERITY_SUPPRESSION_MESSAGE = (
    "Given your recent pattern, consider speaking with a healthcare professional "
    "rather than continuing behavioral adjustments alone."
)

# --- Explicit hard prohibitions (see app.safety.guardrails) ---
# Specific multi-word phrases (not bare words like "diagnos") -- broad
# single-word substrings would false-positive on this module's own
# legitimate disclaimer text (e.g. NON_DIAGNOSTIC_STATEMENT necessarily
# contains the word "diagnosis" in a *negated* sentence). Each entry
# here is a phrase that is prohibited in any form, affirmative or not.
PROHIBITED_PHRASES = (
    "you have dswpd",
    "you have non-24",
    "you have a circadian rhythm disorder",
    "your melatonin level is",
    "your clinical dlmo is",
    "this replaces a sleep study",
    "take melatonin at",
    "use light therapy at",
    "your exact biological clock is",
    "this is a precise measurement",
)

# --- Terms that must never appear anywhere in participant-facing
# recommendation text (a stricter, whole-word/substring check used only
# for validating catalogue recommendation text -- see
# app.safety.catalogue_guard -- where no legitimate behavioral
# recommendation ever needs to mention any of these at all). ---
PROHIBITED_RECOMMENDATION_TERMS = (
    "melatonin", "medication", "dosage", "dose", "prescri", "diagnos", "treatment", "therapy", "mg ",
)
