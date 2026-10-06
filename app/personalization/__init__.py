"""The Phase 13 long-term personalization system.

Graduates each participant/intervention-type pair independently
through LITERATURE -> PERSONAL_RANKING -> PERSONAL_EFFECT ->
ADAPTIVE_POLICY based purely on accumulated intervention-exposure and
compliance evidence (Phase 12's effectiveness output), never on
preference or model confidence alone.

Entry points:
    app.personalization.dispatcher.get_personalization_phase
    app.personalization.dispatcher.personalize_recommendations
    app.personalization.update.update_personalization_state  (offline pipeline)
"""
