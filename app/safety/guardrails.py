"""Explicit language guardrails: nothing this layer emits may contain
any of the hard-prohibited phrases (see ``app.safety.messages.PROHIBITED_PHRASES``).
Every fixed message in this system is already vetted, but this scan
runs defensively over the assembled output text anyway -- a
belt-and-suspenders check, not the only line of defense.
"""

from __future__ import annotations

from app.safety.messages import PROHIBITED_PHRASES


def scan_for_prohibited_language(*texts) -> list:
    """Returns every prohibited phrase found across ``texts`` (case-
    insensitive substring match), or an empty list if none are found."""

    found = []
    for text in texts:
        if not text:
            continue
        lowered = text.lower()
        for phrase in PROHIBITED_PHRASES:
            if phrase in lowered:
                found.append(phrase)
    return found


def assert_no_prohibited_language(*texts) -> None:
    found = scan_for_prohibited_language(*texts)
    if found:
        raise ValueError(f"Prohibited language detected in safety output: {found}")
