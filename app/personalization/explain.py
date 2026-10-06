"""Fixed, structured explanation strings -- no LLM, no dynamically
generated prose. The UI decides how to render these; this module only
picks which fixed template applies to the current personalization
phase (see ``docs/personalization_engine.md`` "Explainability").
"""

from __future__ import annotations

from typing import Optional


def explain_literature() -> str:
    return "Based on circadian research."


def explain_personal_ranking() -> str:
    return "Based on your recent response history."


def explain_personal_effect(intervention_type: str, stronger_than: Optional[str] = None) -> str:
    if stronger_than is not None:
        return f"Your clock has shown a stronger modeled response to {intervention_type} than {stronger_than}."
    return f"Based on your personal response history to {intervention_type}."


def explain_adaptive() -> str:
    return "Selected based on your recent response and current context."
