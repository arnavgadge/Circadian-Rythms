"""The Phase 10 recommendation engine.

Converts Phase 9's ranked contributors into exactly one primary
intervention plus up to two supporting nudges, selected deterministically
from the database intervention catalogue. Entry point:
``app.recommendations.engine.select_recommendations``.
"""
