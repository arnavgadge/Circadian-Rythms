"""Tests for the 30-day deterministic demo scenario (Arjun, participant_id=9001).

Most tests read the already-seeded-and-run demo database
(data/demo_30day_story.db, produced by
`python -m app.scripts.seed_30day_demo --reset` then
`python -m app.scripts.run_30day_demo`) rather than re-running the full
~30-day pipeline inline, which would make the suite slow. A few tests
work directly against the fixed YAML schedule and don't need a
database at all. If the demo database doesn't exist yet, the DB-backed
tests are skipped with a clear message rather than failing --
generating it is a deliberate, explicit step (see
docs/30_day_demo_scenario.md "How to reproduce"), not something the
test suite should do as a side effect.
"""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "demo_30day_story.db"
SCENARIO_PATH = PROJECT_ROOT / "demo" / "scenarios" / "late_screen_recovery_30d.yaml"
OUTPUT_DIR = PROJECT_ROOT / "release" / "demo_30day"
DEMO_PARTICIPANT_ID = 9001

requires_demo_db = pytest.mark.skipif(
    not DB_PATH.exists(),
    reason="data/demo_30day_story.db not seeded -- run `python -m app.scripts.seed_30day_demo --reset && python -m app.scripts.run_30day_demo` first.",
)
requires_demo_reports = pytest.mark.skipif(
    not (OUTPUT_DIR / "daily_summary.csv").exists(),
    reason="release/demo_30day/ reports not generated -- run `python -m app.scripts.run_30day_demo` first.",
)


@pytest.fixture(scope="module")
def demo_session_factory():
    os.environ["CIRCADIANIQ_DATABASE_URL"] = f"sqlite:///{DB_PATH}"
    from app.config.settings import load_config
    from app.database.engine import create_app_engine, create_session_factory

    engine = create_app_engine(load_config())
    return create_session_factory(engine)


# ---------------------------------------------------------------------------
# 1-6: schedule / seeding correctness (no database needed)
# ---------------------------------------------------------------------------


def test_scenario_file_defines_exactly_30_days():
    doc = yaml.safe_load(SCENARIO_PATH.read_text(encoding="utf-8"))
    days = doc["days"]
    assert len(days) == 30
    assert {d["day"] for d in days} == set(range(1, 31))


def test_scenario_stage_boundaries_match_the_brief():
    doc = yaml.safe_load(SCENARIO_PATH.read_text(encoding="utf-8"))
    by_day = {d["day"]: d["stage"] for d in doc["days"]}
    expected = {
        **{d: "STAGE_1_BASELINE" for d in range(1, 8)},
        **{d: "STAGE_2_IDENTIFY" for d in range(8, 11)},
        **{d: "STAGE_3_CHANGE" for d in range(11, 19)},
        **{d: "STAGE_4_RESPONSE" for d in range(19, 25)},
        **{d: "STAGE_5_STABLE" for d in range(25, 31)},
    }
    assert by_day == expected


def _strip_comments_and_docstrings(source: str) -> str:
    """Blank out triple-quoted docstrings and '#' comments (length-preserving
    is unnecessary here) so a negated mention -- e.g. this file's own "no
    numpy.random anywhere" docstring -- doesn't trip a source-code guard
    check the way Phase 17's medical-language scan learned to handle."""

    no_docstrings = re.sub(r'"""[\s\S]*?"""', "", source)
    no_comments = re.sub(r"#.*", "", no_docstrings)
    return no_comments


def test_scenario_has_no_randomness():
    """No actual random/np.random/seed CALL anywhere in the authoring or
    seeding scripts' real code (docstrings that describe this guarantee
    in prose are fine and expected -- see _strip_comments_and_docstrings)."""

    for path in [
        PROJECT_ROOT / "demo" / "scenarios" / "_author_late_screen_recovery_30d.py",
        PROJECT_ROOT / "app" / "scripts" / "seed_30day_demo.py",
    ]:
        code_only = _strip_comments_and_docstrings(path.read_text(encoding="utf-8"))
        assert not re.search(r"\bimport random\b", code_only)
        assert not re.search(r"\bnp\.random\b|\bnumpy\.random\b", code_only)
        assert "random.seed" not in code_only


def test_deterministic_reseeding_produces_identical_observations(tmp_path):
    """Seed the same fixed YAML into two independent fresh databases and
    confirm every daily_observations field is byte-identical -- the key
    executable proof that this scenario is deterministic, not sampled."""

    import subprocess
    import sys

    def _seed(db_path: Path) -> list[dict]:
        subprocess.run(
            [sys.executable, "-m", "app.scripts.seed_30day_demo", "--db-path", str(db_path), "--reset"],
            cwd=str(PROJECT_ROOT), check=True, capture_output=True,
        )
        os.environ["CIRCADIANIQ_DATABASE_URL"] = f"sqlite:///{db_path}"
        from sqlalchemy import select

        from app.config.settings import load_config
        from app.database.engine import create_app_engine, create_session_factory
        from app.database.models import DailyObservation

        engine = create_app_engine(load_config())
        session = create_session_factory(engine)()
        rows = session.execute(
            select(DailyObservation).where(DailyObservation.participant_id == DEMO_PARTICIPANT_ID).order_by(DailyObservation.observation_date)
        ).scalars().all()
        out = [
            {
                "date": str(r.observation_date), "onset": str(r.sleep_onset_time), "screen_end": str(r.evening_screen_end_time),
                "light_start": str(r.morning_light_start_time), "meal": str(r.last_meal_time), "sjl": r.social_jetlag_minutes,
            }
            for r in rows
        ]
        session.close()
        return out

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    rows_a = _seed(db_a)
    rows_b = _seed(db_b)
    assert rows_a == rows_b
    assert len(rows_a) == 30


def test_seeder_refuses_to_target_the_real_or_release_demo_databases(tmp_path):
    import subprocess
    import sys

    for forbidden_name in ("circadianiq.db", "demo.db"):
        result = subprocess.run(
            [sys.executable, "-m", "app.scripts.seed_30day_demo", "--db-path", str(tmp_path / forbidden_name), "--reset"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert not (tmp_path / forbidden_name).exists()


def test_runner_script_never_writes_directly_to_intelligence_result_tables():
    """The demo participant is special only because its INPUT DATA is
    predefined -- system outputs must be real pipeline outputs. This is a
    structural guard: run_30day_demo.py must never session.add(...) one
    of the intelligence-result ORM classes directly."""

    source = (PROJECT_ROOT / "app" / "scripts" / "run_30day_demo.py").read_text(encoding="utf-8")
    forbidden_direct_writes = ["CircadianLabel(", "AlignmentResult(", "ContributorResult(", "InterventionLog(", "PersonalEffectModel("]
    for forbidden in forbidden_direct_writes:
        assert forbidden not in source, f"run_30day_demo.py must never construct {forbidden} directly -- it must come from the real pipeline"
    # It's fine (and expected) that the script *imports* these classes to
    # query/read them for reporting.


# ---------------------------------------------------------------------------
# 7+: real pipeline execution (require the seeded + run database)
# ---------------------------------------------------------------------------


@requires_demo_db
def test_exactly_one_participant(demo_session_factory):
    from sqlalchemy import select

    from app.database.models import Participant

    session = demo_session_factory()
    rows = session.execute(select(Participant)).scalars().all()
    session.close()
    assert len(rows) == 1
    assert rows[0].id == DEMO_PARTICIPANT_ID
    assert rows[0].participant_code.startswith("DEMO-")


@requires_demo_db
def test_no_target_day_leakage_in_committed_predictions(demo_session_factory):
    from sqlalchemy import select

    from app.database.models import CircadianLabel
    from app.pipeline.config import DEFAULT_PIPELINE_CONFIG
    from app.pipeline.read import _consecutive_prior_observations

    session = demo_session_factory()
    labels = session.execute(
        select(CircadianLabel).where(CircadianLabel.participant_id == DEMO_PARTICIPANT_ID, CircadianLabel.is_latest.is_(True))
    ).scalars().all()
    assert len(labels) > 0
    for label in labels:
        window = _consecutive_prior_observations(session, DEMO_PARTICIPANT_ID, label.target_date, DEFAULT_PIPELINE_CONFIG.min_consecutive_history_days)
        assert all(o.observation_date < label.target_date for o in window)
        assert len(window) == DEFAULT_PIPELINE_CONFIG.min_consecutive_history_days
    session.close()


@requires_demo_db
def test_real_xgboost_state_and_fusion_outputs_are_populated(demo_session_factory):
    from sqlalchemy import select

    from app.database.models import CircadianLabel

    session = demo_session_factory()
    success_labels = session.execute(
        select(CircadianLabel).where(CircadianLabel.participant_id == DEMO_PARTICIPANT_ID, CircadianLabel.prediction_status == "success")
    ).scalars().all()
    session.close()
    assert len(success_labels) > 0
    for label in success_labels:
        assert label.xgboost_dlmo_time is not None
        assert label.state_model_dlmo_time is not None
        assert label.fused_dlmo_time is not None


@requires_demo_db
def test_real_alignment_and_contributor_outputs_exist(demo_session_factory):
    from sqlalchemy import select

    from app.database.models import AlignmentResult, CircadianLabel, ContributorResult

    session = demo_session_factory()
    alignment_rows = session.execute(select(AlignmentResult).join(CircadianLabel).where(CircadianLabel.participant_id == DEMO_PARTICIPANT_ID)).scalars().all()
    contributor_rows = session.execute(select(ContributorResult).join(AlignmentResult).join(CircadianLabel).where(CircadianLabel.participant_id == DEMO_PARTICIPANT_ID)).scalars().all()
    session.close()
    assert len(alignment_rows) > 0
    assert all(0.0 <= r.final_alignment_score <= 100.0 for r in alignment_rows)
    assert len(contributor_rows) > 0


@requires_demo_db
def test_real_recommendations_and_compliance_evaluation(demo_session_factory):
    from sqlalchemy import select

    from app.database.models import InterventionLog

    session = demo_session_factory()
    logs = session.execute(select(InterventionLog).where(InterventionLog.participant_id == DEMO_PARTICIPANT_ID)).scalars().all()
    session.close()
    assert len(logs) > 0
    with_compliance = [l for l in logs if l.compliance_degree is not None]
    assert len(with_compliance) > 0
    # Compliance must genuinely vary -- a constant value across every day
    # would indicate a hard-coded number rather than a real per-day
    # comparison of actual behavior against that day's target.
    distinct_values = {round(l.compliance_degree, 4) for l in with_compliance}
    assert len(distinct_values) > 1, "compliance_degree never varies -- looks hard-coded, not computed"


@requires_demo_db
def test_intervention_effect_estimates_were_computed(demo_session_factory):
    from sqlalchemy import select

    from app.database.models import InterventionEffectEstimate

    session = demo_session_factory()
    rows = session.execute(select(InterventionEffectEstimate).where(InterventionEffectEstimate.participant_id == DEMO_PARTICIPANT_ID)).scalars().all()
    session.close()
    assert len(rows) > 0
    assert all(r.measurement_phase in (1, 2, 3) for r in rows)


@requires_demo_db
def test_personalization_follows_real_graduation_rules(demo_session_factory):
    from sqlalchemy import select

    from app.database.models import PersonalEffectModel
    from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG

    session = demo_session_factory()
    models = session.execute(select(PersonalEffectModel).where(PersonalEffectModel.participant_id == DEMO_PARTICIPANT_ID)).scalars().all()
    session.close()
    assert len(models) > 0
    valid_phases = {"literature", "personal_ranking", "personal_effect", "adaptive_policy"}
    for m in models:
        assert m.personalization_phase in valid_phases
        if m.personalization_phase == "adaptive_policy":
            assert m.num_observations >= DEFAULT_PERSONALIZATION_CONFIG.adaptive_min_observations


@requires_demo_db
def test_database_isolated_from_real_and_release_demo_databases():
    assert DB_PATH.name == "demo_30day_story.db"
    assert DB_PATH.name not in ("circadianiq.db", "demo.db")


@requires_demo_db
def test_frontend_api_can_load_the_demo_participant(demo_session_factory):
    """The existing API/frontend need no special-casing for this
    participant -- GET /status must just work, same as any other id."""

    os.environ["CIRCADIANIQ_DATABASE_URL"] = f"sqlite:///{DB_PATH}"
    from fastapi.testclient import TestClient

    from app.api.main import create_app

    with TestClient(create_app()) as client:
        response = client.get(f"/api/v1/participants/{DEMO_PARTICIPANT_ID}/status")
    assert response.status_code == 200
    body = response.json()
    assert body["participant_id"] == DEMO_PARTICIPANT_ID


# ---------------------------------------------------------------------------
# reports (require release/demo_30day/ to have been generated)
# ---------------------------------------------------------------------------


@requires_demo_reports
def test_daily_summary_csv_has_one_row_per_predicted_day():
    rows = list(csv.DictReader((OUTPUT_DIR / "daily_summary.csv").open(encoding="utf-8")))
    days = sorted(int(r["day"]) for r in rows)
    assert days == list(range(7, 31))


@requires_demo_reports
def test_all_five_checkpoints_generated():
    for day in (7, 10, 18, 24, 30):
        path = OUTPUT_DIR / "checkpoints" / f"checkpoint_day_{day}.json"
        assert path.exists(), f"missing {path}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["day"] == day


@requires_demo_reports
def test_demo_story_report_carries_the_synthetic_disclaimer():
    text = (OUTPUT_DIR / "demo_story.md").read_text(encoding="utf-8")
    assert "deterministic synthetic demonstration participant" in text
    assert "clinical dlmo" not in text.lower()
    # "proven causal effect" may legitimately appear in a negation ("never
    # a proven causal effect"); what must never appear is an affirmative
    # causal claim.
    assert not re.search(r"\bwas a proven causal effect\b|\bproves? (a |the )?caus", text.lower())


@requires_demo_reports
def test_seven_figures_generated():
    figures_dir = OUTPUT_DIR / "figures"
    pngs = sorted(figures_dir.glob("*.png"))
    assert len(pngs) == 7
