"""
Tests for the security controls (see brain/security/).

  SEC-01/03/04  app configuration: localhost binding, hidden error details, XSRF/CORS on
  SEC-02        per-session rate limiting
  SEC-05        model-file integrity manifest
  SEC-06        predictor input validation, and the app handling bad input gracefully
"""

import math
from pathlib import Path

import numpy as np
import pytest
import tomllib

from cardiostage import config, integrity, ratelimit
from cardiostage.predictor import CardioStagePredictor, InvalidInputError

ROOT = Path(__file__).resolve().parents[1]
MODELS_PRESENT = all((config.MODELS_DIR / f"stage{s}.joblib").exists() for s in config.STAGES)


# ------------------------------------------------- SEC-01/03/04: configuration --
@pytest.fixture(scope="module")
def streamlit_config():
    with open(ROOT / ".streamlit" / "config.toml", "rb") as f:
        return tomllib.load(f)


def test_server_listens_on_localhost_only(streamlit_config):
    # A blank/wildcard address exposes the app to the whole network (SEC-01)
    # and triggers Streamlit's external-IP lookup at startup (SEC-04).
    assert streamlit_config["server"]["address"] == "localhost"


def test_error_details_hidden_from_users(streamlit_config):
    assert streamlit_config["client"]["showErrorDetails"] == "none"


def test_framework_protections_explicitly_on(streamlit_config):
    assert streamlit_config["server"]["enableXsrfProtection"] is True
    assert streamlit_config["server"]["enableCORS"] is True
    assert streamlit_config["browser"]["gatherUsageStats"] is False
    assert streamlit_config["server"].get("enableAgentApi", False) is False


# --------------------------------------------------------- SEC-02: rate limit --
def test_rate_limit_allows_up_to_limit_then_blocks():
    times = []
    for i in range(5):
        allowed, times, _ = ratelimit.check_and_record(times, 100.0 + i, 5, 60)
        assert allowed
    allowed, times, wait = ratelimit.check_and_record(times, 105.0, 5, 60)
    assert not allowed
    assert len(times) == 5  # blocked event not recorded
    assert wait == pytest.approx(55.0)  # oldest (t=100) expires at t=160


def test_rate_limit_window_slides():
    times = [0.0, 1.0, 2.0]
    allowed, times, _ = ratelimit.check_and_record(times, 61.5, 3, 60)
    assert allowed  # events at t=0 and t=1 have expired
    assert times == [2.0, 61.5]


def test_rate_limit_default_never_blocks_a_normal_screening():
    times = []
    for stage_time in (0.0, 5.0, 10.0):  # a full 3-stage screening
        allowed, times, _ = ratelimit.check_and_record(times, stage_time)
        assert allowed


# --------------------------------------------------- SEC-05: model integrity --
def test_integrity_accepts_untouched_file_and_rejects_tampering(tmp_path):
    bundle = tmp_path / "stage1.joblib"
    bundle.write_bytes(b"original model bytes")
    manifest = tmp_path / "manifest.json"
    integrity.write_manifest([bundle], manifest)
    integrity.verify(bundle, manifest)  # passes

    bundle.write_bytes(b"tampered model bytes")
    with pytest.raises(integrity.IntegrityError, match="fingerprint"):
        integrity.verify(bundle, manifest)


def test_integrity_rejects_unlisted_file_and_missing_manifest(tmp_path):
    listed, unlisted = tmp_path / "a.joblib", tmp_path / "b.joblib"
    listed.write_bytes(b"a")
    unlisted.write_bytes(b"b")
    manifest = tmp_path / "manifest.json"
    integrity.write_manifest([listed], manifest)
    with pytest.raises(integrity.IntegrityError, match="not listed"):
        integrity.verify(unlisted, manifest)
    with pytest.raises(integrity.IntegrityError, match="No integrity manifest"):
        integrity.verify(listed, tmp_path / "absent.json")


def test_integrity_load_refuses_before_unpickling(tmp_path):
    import joblib

    good = tmp_path / "x.joblib"
    joblib.dump({"ok": 1}, good)
    manifest = tmp_path / "manifest.json"
    integrity.write_manifest([good], manifest)
    assert integrity.load(good, manifest) == {"ok": 1}
    joblib.dump({"evil": 1}, good)  # replaced after the manifest was written
    with pytest.raises(integrity.IntegrityError):
        integrity.load(good, manifest)


@pytest.mark.skipif(not MODELS_PRESENT, reason="trained models missing")
def test_real_bundles_match_manifest():
    for path in integrity.stage_bundle_paths():
        integrity.verify(path)


# ------------------------------------------------- SEC-06: input validation --
FEATURES = config.STAGES[3]
VALID = dict(
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


def test_valid_patient_and_missing_values_accepted():
    frame = CardioStagePredictor.to_frame(dict(VALID, chol=None, thal=None), FEATURES)
    assert math.isnan(frame.loc[0, "chol"]) and frame.loc[0, "thal"] != frame.loc[0, "thal"]


@pytest.mark.parametrize(
    "field, value",
    [
        ("cp", "sharp pain"),  # unknown category
        ("fbs", "abc"),  # not a number
        ("fbs", 2.0),  # not an allowed code
        ("exang", 0.5),
        ("ca", 7),
        ("sex", 3.0),
        ("age", float("inf")),  # non-finite
        ("age", 250),  # physically implausible
        ("trestbps", 10),
        ("oldpeak", 50.0),
        ("chol", "1e309"),  # parses to infinity
    ],
)
def test_invalid_inputs_rejected(field, value):
    with pytest.raises(InvalidInputError):
        CardioStagePredictor.to_frame(dict(VALID, **{field: value}), FEATURES)


def test_numeric_strings_accepted():
    frame = CardioStagePredictor.to_frame(dict(VALID, age="61"), FEATURES)
    assert frame.loc[0, "age"] == 61.0 and np.issubdtype(frame["age"].dtype, np.number)


@pytest.mark.skipif(not MODELS_PRESENT, reason="trained models missing")
@pytest.mark.parametrize(
    "error, expected_text",
    [
        (InvalidInputError("fbs must be one of [0.0, 1.0], got 'x'"), "aren't valid"),
        (RuntimeError("internal failure at D:/secret/path.py"), "Something went wrong"),
    ],
)
def test_app_shows_friendly_errors_not_tracebacks(monkeypatch, error, expected_text):
    """
    If an assessment fails (bad input from a crafted request, or an unexpected
    bug), users get a friendly message: no traceback, no internal details.
    (Streamlit's test harness can't send out-of-option widget values, so we
    make the assessment raise instead.)
    """
    from streamlit.testing.v1 import AppTest

    def failing_assess(self, patient, stage, **kwargs):
        raise error

    monkeypatch.setattr(CardioStagePredictor, "assess", failing_assess)
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=180).run()
    next(b for b in at.button if b.label == "Assess risk").click().run()

    assert not at.exception  # no traceback element rendered
    messages = [e.value for e in at.error]
    assert any(expected_text in m for m in messages)
    assert not any("secret/path" in m for m in messages)  # internals never shown
    assert 1 not in at.session_state.results
