"""AUDIT 18 -- Medical language audit.

Repository-wide, grep-based scan of user-facing string-literal source
(backend ``app/`` and frontend ``frontend/src/``) for prohibited
medical/clinical language, per ``docs/safety_and_confidence.md``
sections 10-12 ("Wellness boundary," "Prohibited claims," "Intervention
catalogue validation").

This is a defense-in-depth, build-breaking check on top of the
runtime guards already in ``app.safety.guardrails`` and
``app.safety.catalogue_guard`` -- it catches a prohibited phrase
introduced anywhere in the tree, not just in the specific strings
those two modules happen to scan at runtime.

--- Exclusion rationale (read before editing the SCAN_EXCLUDE_FILES list) ---

``app/safety/messages.py`` and ``app/safety/guardrails.py`` are
QUARANTINED POLICY-DATA modules: ``PROHIBITED_PHRASES`` and
``PROHIBITED_RECOMMENDATION_TERMS`` necessarily contain the very
phrases this audit blocks, as blocklist *data*, not as text that is
ever rendered to a participant. Excluding these two files (rather than
trying to regex around "blocklist tuple vs. display string" within a
single file) is the simplest correct rule and matches the guidance in
the audit brief. Everything else in ``app/`` and ``frontend/src/`` is
scanned as real, potentially user-facing source.

``app/scripts/validate_30day_demo.py`` (the 30-day demo scenario's own
narrative-quality checker, Phase 18 add-on) is excluded for the exact
same reason: it defines a small local blocklist of the same prohibited
terms to scan ``release/demo_30day/demo_story.md`` for, as data, never
as display text of its own.

Frontend test files (``frontend/src/test/``) and component/page tests
(``**/__tests__/**``) are also excluded: they legitimately assert
*absence* of prohibited phrases (e.g. "not a diagnosis," "clinical
DLMO" negative-assertions), so their source text contains the
blocked substrings by design, as test data, not as display text.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from app.safety.messages import BOUNDARY_NOTE_SHORT, NON_DIAGNOSTIC_STATEMENT

REPO_ROOT = Path(__file__).resolve().parents[2]

BACKEND_ROOT = REPO_ROOT / "app"
FRONTEND_ROOT = REPO_ROOT / "frontend" / "src"

# Files that legitimately hold prohibited-phrase blocklist *data* (see
# module docstring above) -- not participant-facing display text.
SCAN_EXCLUDE_FILES = {
    (BACKEND_ROOT / "safety" / "messages.py").resolve(),
    (BACKEND_ROOT / "safety" / "guardrails.py").resolve(),
    (BACKEND_ROOT / "scripts" / "validate_30day_demo.py").resolve(),
}

# Directories excluded outright (backend): caches, generated data, and
# the tests tree itself (audit tests and fixtures legitimately name
# prohibited phrases as test data, never as display text).
BACKEND_EXCLUDE_DIR_NAMES = {"__pycache__", "tests", "migrations", "docs"}

# Frontend: exclude the vitest test tree (assertions/fixtures
# legitimately reference the blocked phrases as expected-absent test
# data) and generated/build dirs.
FRONTEND_EXCLUDE_DIR_PARTS = {"test", "__tests__", "node_modules", "dist", "build"}


def _iter_backend_files():
    for dirpath, dirnames, filenames in os.walk(BACKEND_ROOT):
        dirnames[:] = [d for d in dirnames if d not in BACKEND_EXCLUDE_DIR_NAMES]
        for name in filenames:
            if name.endswith(".py"):
                path = Path(dirpath) / name
                if path.resolve() not in SCAN_EXCLUDE_FILES:
                    yield path


def _iter_frontend_files():
    if not FRONTEND_ROOT.exists():
        return
    for dirpath, dirnames, filenames in os.walk(FRONTEND_ROOT):
        dirnames[:] = [d for d in dirnames if d not in FRONTEND_EXCLUDE_DIR_PARTS]
        for name in filenames:
            if name.endswith((".ts", ".tsx")):
                yield Path(dirpath) / name


# ---------------------------------------------------------------------------
# Blocklist: specific multi-word phrases / anchored patterns, mirroring
# app.safety.messages.PROHIBITED_PHRASES's strategy of avoiding bare
# single words (e.g. "disorder," "diagnos") that appear legitimately in
# negated disclaimer sentences ("does not diagnose any condition,"
# "circadian rhythm disorders" as a generic plural in a negation).
# ---------------------------------------------------------------------------

BLOCKLIST_PATTERNS = [
    # -- Diagnosis claims (affirmative, about the specific user) --
    r"you have (dswpd|non-24|a circadian rhythm disorder|delayed sleep)",
    r"you are diagnosed",
    r"diagnosed with",
    r"we diagnose",
    r"this diagnoses",
    # -- Clinical DLMO / false-precision claims --
    r"clinical dlmo",
    r"measured dlmo",
    r"your exact dlmo",
    r"laboratory dlmo",
    r"your exact biological clock is",
    r"this is a precise measurement",
    r"your melatonin level is",
    r"your clinical dlmo is",
    # -- Melatonin dosing / medication / dosage language --
    r"take melatonin",
    r"melatonin dose",
    r"melatonin dosage",
    r"\d+\s?mg of melatonin",
    r"prescri(be|ption|bed)",
    # -- Sleep-study-replacement / doctor-replacement claims --
    r"replaces a sleep study",
    r"instead of seeing a doctor",
    r"instead of a doctor",
    r"in place of a doctor",
    r"no need to see a doctor",
    # -- False clinical-validation / accuracy claims --
    r"accuracy in humans",
    r"clinically validated accuracy",
    r"fda[- ]?(approved|cleared)",
]

_COMPILED = [(p, re.compile(p, re.IGNORECASE)) for p in BLOCKLIST_PATTERNS]

# Comment/docstring stripping: per the audit brief, a match that occurs
# only inside a comment or docstring *documenting the prohibition
# itself* (e.g. a module docstring saying 'never "Clinical DLMO"', or
# a code comment explaining why real DLMO isn't used) is not a
# participant-facing violation. Rather than trying to classify intent,
# we blank out comment/docstring regions before scanning -- this is a
# deliberately conservative choice (it can only cause us to miss a
# violation that exists *only* inside a comment, which would itself be
# dead/non-shipped text) in exchange for not false-positiving on
# legitimate developer documentation. Blanking preserves string length
# and newlines so reported line numbers stay accurate.


def _blank_span(match: "re.Match") -> str:
    return "".join(ch if ch == "\n" else " " for ch in match.group(0))


_PY_TRIPLE_QUOTED = re.compile(r'("""|\'\'\')(?:.|\n)*?\1')
_PY_LINE_COMMENT = re.compile(r"#[^\n]*")
_TS_BLOCK_COMMENT = re.compile(r"/\*(?:.|\n)*?\*/")
_TS_LINE_COMMENT = re.compile(r"//[^\n]*")


def _strip_non_display_text(text: str, suffix: str) -> str:
    if suffix == ".py":
        text = _PY_TRIPLE_QUOTED.sub(_blank_span, text)
        text = _PY_LINE_COMMENT.sub(_blank_span, text)
    else:  # .ts / .tsx
        text = _TS_BLOCK_COMMENT.sub(_blank_span, text)
        text = _TS_LINE_COMMENT.sub(_blank_span, text)
    return text


def _scan_file(path: Path):
    """Returns a list of (pattern, line_no, line_text) violations, with
    comments/docstrings blanked out first (see module docstring)."""

    try:
        raw_text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    text = _strip_non_display_text(raw_text, path.suffix)

    violations = []
    lines = raw_text.splitlines()
    for pattern_str, pattern in _COMPILED:
        for match in pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            line_text = lines[line_no - 1].strip() if 0 < line_no <= len(lines) else ""
            violations.append((pattern_str, line_no, line_text))
    return violations


def _scan_tree(files):
    all_violations = []
    for path in files:
        for pattern_str, line_no, line_text in _scan_file(path):
            all_violations.append(f"{path}:{line_no}  [pattern={pattern_str!r}]  {line_text}")
    return all_violations


# ---------------------------------------------------------------------------
# Main scans.
# ---------------------------------------------------------------------------


def test_backend_app_tree_has_no_prohibited_medical_language():
    violations = _scan_tree(_iter_backend_files())
    assert not violations, (
        "Prohibited medical/clinical language found in app/ source "
        "(participant-facing scope). Violations:\n" + "\n".join(violations)
    )


def test_frontend_src_tree_has_no_prohibited_medical_language():
    violations = _scan_tree(_iter_frontend_files())
    assert not violations, (
        "Prohibited medical/clinical language found in frontend/src source "
        "(participant-facing scope). Violations:\n" + "\n".join(violations)
    )


def test_raw_accuracy_percentage_claims_have_synthetic_framing_or_dont_exist():
    """Any bare 'X% accuracy' string must either not exist, or (if it
    does, e.g. in an internal diagnostics report) be framed with
    'synthetic' / 'test window' / 'held-out' nearby so it cannot read as
    a clinical-validation claim. This is a hand-checked finding, not a
    hard regex block, per the audit brief."""

    pct_pattern = re.compile(r"\d+(\.\d+)?%\s*accuracy", re.IGNORECASE)
    context_pattern = re.compile(r"synthetic|test window|held-out|held out", re.IGNORECASE)

    findings = []
    for path in list(_iter_backend_files()) + list(_iter_frontend_files()):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for match in pct_pattern.finditer(text):
            start = max(0, match.start() - 200)
            end = min(len(text), match.end() + 200)
            window = text[start:end]
            if not context_pattern.search(window):
                line_no = text.count("\n", 0, match.start()) + 1
                findings.append(f"{path}:{line_no}  {match.group(0)!r} (no synthetic/test-window framing nearby)")

    assert not findings, (
        "Found raw 'X% accuracy' claim(s) without synthetic/held-out framing "
        "-- these read as clinical-validation claims and must be reworded or "
        "reframed. Findings:\n" + "\n".join(findings)
    )


# ---------------------------------------------------------------------------
# Positive confirmation: the approved/allowed wellness-boundary
# terminology is present and unchanged (guards against a future edit
# quietly weakening the disclaimer language rather than replacing it
# with something prohibited outright).
# ---------------------------------------------------------------------------


def test_backend_allowed_boundary_terminology_is_intact():
    assert BOUNDARY_NOTE_SHORT == "Estimated from behavioral patterns. Not a clinical measurement."
    assert NON_DIAGNOSTIC_STATEMENT == (
        "This is a pattern observation, not a medical diagnosis. "
        "CircadianIQ does not diagnose sleep or circadian rhythm disorders."
    )


def test_frontend_allowed_terminology_constants_are_intact():
    messages_ts = (FRONTEND_ROOT / "utils" / "messages.ts").read_text(encoding="utf-8")
    terminology_ts = (FRONTEND_ROOT / "utils" / "terminology.ts").read_text(encoding="utf-8")

    assert (
        'export const NON_DIAGNOSTIC_STATEMENT = "This is not a diagnosis.";' in messages_ts
    )
    assert (
        "CircadianIQ estimates your circadian phase from behavioral patterns. "
        "It is not a medical device, does not perform laboratory measurements, "
        "and does not diagnose any condition." in messages_ts
    )
    assert 'export const HIGH_SEVERITY_BODY = "CircadianIQ cannot diagnose circadian rhythm disorders.";' in messages_ts
    assert 'moderate: "Estimated from partial data."' in messages_ts

    assert 'MODERATE: "Pattern note"' in terminology_ts
    assert 'HIGH: "Safety note"' in terminology_ts


def test_biological_clock_card_uses_estimated_not_clinical_terminology():
    """Spot-check the specific component the audit brief calls out by
    name: it must render 'Estimated Biological Clock' and must not
    render 'Clinical DLMO' as display text (the phrase 'Clinical DLMO'
    does legitimately appear once, inside a JSDoc comment documenting
    this very prohibition -- that occurrence is stripped by
    ``_strip_non_display_text`` before this check, same as the
    repository-wide scan above)."""

    path = FRONTEND_ROOT / "components" / "BiologicalClockCard.tsx"
    raw_card = path.read_text(encoding="utf-8")
    display_only = _strip_non_display_text(raw_card, path.suffix)

    assert "Estimated Biological Clock" in raw_card
    assert "Clinical DLMO" not in display_only
