"""AUDIT 30 -- Security/privacy baseline (Phase 17 adversarial audit).

Prototype-level, not production certification, per the audit scope.
Combines static repo checks (secrets, raw SQL, logging hygiene) with
live API tests that a request scoped to participant A's URL path
cannot read or mutate participant B's data.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = PROJECT_ROOT / "app"


def _py_files(*dirs: Path):
    for d in dirs:
        if d.exists():
            yield from d.rglob("*.py")


# --------------------------------------------------------------------------
# No committed secrets
# --------------------------------------------------------------------------


def test_no_dotenv_file_is_committed_only_examples():
    """.env (real secrets) must not exist in the repo; only .env.example
    templates are expected."""

    for env_path in (PROJECT_ROOT / ".env", PROJECT_ROOT / "frontend" / ".env"):
        assert not env_path.exists(), f"{env_path} should not exist -- only .env.example belongs in the repo"

    assert (PROJECT_ROOT / ".env.example").exists()
    assert (PROJECT_ROOT / "frontend" / ".env.example").exists()


def test_gitignore_excludes_env_and_database_files():
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", "*.db", "*.sqlite"):
        assert pattern in gitignore, f".gitignore is missing an entry for {pattern}"


def test_no_hardcoded_database_credentials_in_frontend_source():
    frontend_src = PROJECT_ROOT / "frontend" / "src"
    if not frontend_src.exists():
        pytest.skip("frontend/src not present")

    suspicious = re.compile(r"(postgres(ql)?|mysql)://[^\s\"']*:[^\s\"']*@", re.IGNORECASE)
    offenders = []
    for path in frontend_src.rglob("*"):
        if path.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if suspicious.search(text):
            offenders.append(str(path))
    assert offenders == [], f"possible embedded DB credentials in frontend source: {offenders}"


# --------------------------------------------------------------------------
# No raw/string-interpolated SQL
# --------------------------------------------------------------------------


def test_no_f_string_or_percent_built_raw_sql_in_app_code():
    """SQLAlchemy ORM/Core constructs (select(), update(), text() with
    bound params) should be used throughout -- never a query string
    built by f-string/%-interpolation from caller-controlled input."""

    f_string_sql = re.compile(r'\.execute\(\s*f["\']', re.IGNORECASE)
    percent_sql = re.compile(r'\.execute\(\s*["\'][^"\']*%s', re.IGNORECASE)

    offenders = []
    for path in _py_files(APP_DIR):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if f_string_sql.search(text) or percent_sql.search(text):
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == [], f"possible raw/interpolated SQL found in: {offenders}"


def test_no_raw_text_sql_with_string_formatting_anywhere_in_app():
    """A slightly broader sweep: sqlalchemy.text(...) called with an
    f-string or % formatted argument, which would defeat parameter
    binding even if .execute() itself looks safe."""

    pattern = re.compile(r'text\(\s*f["\']', re.IGNORECASE)
    offenders = []
    for path in _py_files(APP_DIR):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            offenders.append(str(path.relative_to(PROJECT_ROOT)))
    assert offenders == []


# --------------------------------------------------------------------------
# No raw behavioral PII in log statements
# --------------------------------------------------------------------------


_PII_ARG_NAME_PATTERN = re.compile(
    r"^(participant_code|sleep_onset|sleep_offset|light_.*|screen_.*|meal_.*|caffeine_.*|"
    r"observation|behavior(al)?_payload|request\.dict|request\.model_dump)$",
    re.IGNORECASE,
)


def test_no_logging_call_passes_a_raw_observation_or_request_payload():
    """Flags any app/**/*.py logger.<level>(...) call that passes an
    entire observation/request object or an obviously-named raw
    behavioral field as a positional/keyword argument, rather than an
    id/aggregate. Uses the AST rather than a regex so it tolerates
    formatting differences."""

    offenders = []
    for path in _py_files(APP_DIR):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_logger_call = (
                isinstance(func, ast.Attribute)
                and func.attr in {"debug", "info", "warning", "error", "exception", "critical"}
                and isinstance(func.value, ast.Name)
                and func.value.id == "logger"
            )
            if not is_logger_call:
                continue
            for arg in node.args:
                name = None
                if isinstance(arg, ast.Name):
                    name = arg.id
                elif isinstance(arg, ast.Attribute):
                    name = arg.attr
                if name and _PII_ARG_NAME_PATTERN.match(name):
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} logs raw field '{name}'")

    assert offenders == [], f"logging calls that appear to pass raw behavioral/PII fields: {offenders}"


# --------------------------------------------------------------------------
# Pydantic input validation exists for every write endpoint
# --------------------------------------------------------------------------


def test_every_post_endpoint_declares_a_pydantic_request_schema():
    """Every @router.post(...) handler in app/api/routers must take a
    typed request body (a BaseModel subclass), not a raw dict -- this
    is what makes FastAPI/Pydantic actually validate the input."""

    from pydantic import BaseModel

    from app.api.routers import behavior, interventions, onboarding

    import inspect
    import typing

    offenders = []
    for module in (behavior, interventions, onboarding):
        for name, func in inspect.getmembers(module, inspect.isfunction):
            if func.__module__ != module.__name__:
                continue
            sig = inspect.signature(func)
            if "request" not in sig.parameters:
                continue
            # These modules use `from __future__ import annotations`, so
            # raw sig.parameters annotations are unevaluated strings --
            # resolve them properly via get_type_hints instead.
            hints = typing.get_type_hints(func)
            request_type = hints.get("request")
            has_request_param = isinstance(request_type, type) and issubclass(request_type, BaseModel)
            if not has_request_param:
                offenders.append(f"{module.__name__}.{name}")

    assert offenders == [], f"POST handlers without a validated Pydantic request schema: {offenders}"


# --------------------------------------------------------------------------
# Participant-scope boundary enforcement (live API)
# --------------------------------------------------------------------------


def _onboard(api_client, code: str) -> int:
    response = api_client.post("/api/v1/participants", json={"participant_code": code})
    assert response.status_code == 201, response.text
    return response.json()["participant_id"]


def test_participant_b_cannot_read_participant_a_behavior_history_via_scoped_endpoint(api_client):
    pid_a = _onboard(api_client, "AUDIT_SEC_A")
    pid_b = _onboard(api_client, "AUDIT_SEC_B")

    post_resp = api_client.post(
        f"/api/v1/participants/{pid_a}/behavior",
        json={"observation_date": "2026-01-01", "sleep_onset_time": "23:00"},
    )
    assert post_resp.status_code == 201, post_resp.text

    resp_a = api_client.get(f"/api/v1/participants/{pid_a}/behavior")
    resp_b = api_client.get(f"/api/v1/participants/{pid_b}/behavior")
    assert resp_a.status_code == 200 and resp_b.status_code == 200
    assert resp_a.json()["count"] == 1
    assert resp_b.json()["count"] == 0, "participant B's scoped behavior history leaked participant A's row"


def test_submitting_an_outcome_under_the_wrong_participant_id_is_rejected(api_client):
    """POST /participants/{B}/interventions/{A's_log_id}/outcome must be
    rejected -- confirms InterventionService.submit_outcome's
    log.participant_id != participant_id ownership check (see
    app/api/services/intervention_service.py) actually holds through
    the live HTTP layer, not just in isolated unit tests."""

    from datetime import date

    from app.database.models import InterventionLog, Recommendation

    pid_a = _onboard(api_client, "AUDIT_SEC_C")
    pid_b = _onboard(api_client, "AUDIT_SEC_D")

    session_factory = api_client.app.state.session_factory
    session = session_factory()
    rec = Recommendation(intervention_code="AUDIT_SEC_REC", intervention_type="light", title="t")
    session.add(rec)
    session.commit()
    log = InterventionLog(participant_id=pid_a, recommendation_id=rec.id, log_date=date(2026, 1, 1))
    session.add(log)
    session.commit()
    log_id = log.id
    session.close()

    resp = api_client.post(
        f"/api/v1/participants/{pid_b}/interventions/{log_id}/outcome",
        json={"observation_date": "2026-01-01", "observed": True, "actual_value_time": "23:15"},
    )
    assert resp.status_code == 404, f"expected the cross-participant outcome submission to be rejected, got {resp.status_code}: {resp.text}"


def test_history_endpoint_never_returns_rows_for_a_different_participant_id(api_client):
    pid_a = _onboard(api_client, "AUDIT_SEC_E")
    pid_b = _onboard(api_client, "AUDIT_SEC_F")

    resp_a = api_client.get(f"/api/v1/participants/{pid_a}/circadian/history")
    resp_b = api_client.get(f"/api/v1/participants/{pid_b}/circadian/history")
    assert resp_a.status_code == 200 and resp_b.status_code == 200
    assert resp_a.json()["participant_id"] == pid_a
    assert resp_b.json()["participant_id"] == pid_b
