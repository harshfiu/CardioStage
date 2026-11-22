"""
Tests for the decision engine (predictor.py) and a smoke test of the app.

These need the trained models in models/ (not stored in Git). If they're
missing, the tests are skipped with a hint instead of failing:
    python -m cardiostage.train_all
"""

import math
from pathlib import Path

import pytest

from cardiostage import config

MODELS_PRESENT = all((config.MODELS_DIR / f"stage{s}.joblib").exists() for s in config.STAGES)
needs_models = pytest.mark.skipif(
    not MODELS_PRESENT, reason="trained models missing: run python -m cardiostage.train_all"
)

PATIENT = dict(
    age=54,
    sex=1.0,
    cp="non-anginal",
    trestbps=135,
    chol=250,
    fbs=0.0,
    restecg="normal",
    thalch=165,
    exang=0.0,
    oldpeak=0.4,
    slope="upsloping",
    ca=0,
    thal="normal",
)


@pytest.fixture(scope="module")
def predictor():
    from cardiostage.predictor import CardioStagePredictor

    return CardioStagePredictor.load()


@needs_models
@pytest.mark.parametrize("stage", [1, 2, 3])
def test_assessment_is_complete_and_consistent(predictor, stage):
    r = predictor.assess(PATIENT, stage)
    assert 0 <= r.risk <= 1 and 0 <= r.range_low <= r.range_high <= 1
    assert r.zone in ({"low", "high", "uncertain"} if stage < 3 else {"refer", "clear"})
    # Explanation adds up to the risk shown.
    assert r.baseline + r.explanation["contribution"].sum() == pytest.approx(r.risk, abs=1e-6)
    assert r.summary.startswith(f"Estimated risk {r.risk:.0%}")


@needs_models
def test_zones_follow_thresholds(predictor):
    z = predictor.bundles[1]["zones"]
    assert predictor.zone(1, z["rule_out_below"] - 1e-6) == "low"
    assert predictor.zone(1, z["rule_in_from"]) == "high"
    middle = (z["rule_out_below"] + z["rule_in_from"]) / 2
    assert predictor.zone(1, middle) == "uncertain"
    t = predictor.bundles[3]["zones"]["screening_threshold"]
    assert predictor.zone(3, t) == "refer" and predictor.zone(3, t - 1e-6) == "clear"


@needs_models
def test_missing_values_and_unusual_patient(predictor):
    odd = dict(PATIENT, age=29, chol=590, fbs=None)
    r = predictor.assess(odd, 1, explain=False)
    assert "fbs" in r.not_measured
    assert any("chol" in reason for reason in r.unusual)
    assert not math.isnan(r.risk)


@needs_models
def test_invalid_category_rejected(predictor):
    with pytest.raises(ValueError):
        predictor.assess(dict(PATIENT, cp="sharp pain"), 1, explain=False)


@needs_models
def test_app_runs_full_flow():
    """Drive the real Streamlit app headlessly through all three stages."""
    from streamlit.testing.v1 import AppTest

    app = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
    at = AppTest.from_file(str(app), default_timeout=180).run()
    assert not at.exception
    at.selectbox(key="example").set_value("Uncertain, then cleared").run()
    assert at.session_state.age == 54  # example loaded into the form

    def click(label):
        next(b for b in at.button if b.label == label).click().run()
        assert not at.exception

    click("Assess risk")
    assert at.session_state.results[1].zone == "uncertain"  # -> treadmill suggested
    click("Add treadmill results")
    assert at.session_state.results[2].zone == "uncertain"  # -> imaging suggested
    click("Add imaging results")
    assert at.session_state.results[3].zone == "clear"  # reassuring tests: cleared


@needs_models
def test_fast_path_then_progressive_details(predictor):
    """The app gets the decision first, then adds range and explanation."""
    r = predictor.assess(PATIENT, 3, explain=False, with_range=False)
    assert r.zone in {"refer", "clear"} and 0 <= r.risk <= 1
    assert not r.has_range and not r.has_explanation
    predictor.add_range(r)
    predictor.add_explanation(r)
    assert r.has_range and r.has_explanation
    full = predictor.assess(PATIENT, 3)
    assert r.risk == full.risk and r.range_low == full.range_low


@needs_models
def test_explanations_are_reproducible(predictor):
    """Same patient twice -> identical explanation (SHAP re-seeded per call)."""
    a = predictor.assess(PATIENT, 2, with_range=False)
    b = predictor.assess(PATIENT, 2, with_range=False)
    assert a.explanation["contribution"].tolist() == b.explanation["contribution"].tolist()


@needs_models
def test_reset_clears_example_and_inputs():
    from streamlit.testing.v1 import AppTest

    app = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
    at = AppTest.from_file(str(app), default_timeout=180).run()
    at.selectbox(key="example").set_value("Known limitation").run()
    assert at.session_state.age == 57 and any("known weakness" in i.value for i in at.info)
    next(b for b in at.button if b.label == "Reset all inputs").click().run()
    assert not at.exception
    assert at.session_state.example == "(enter my own)"
    assert at.session_state.age == 55
    assert not any("known weakness" in i.value for i in at.info)
