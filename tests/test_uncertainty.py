"""Tests for calibration helpers (calibration.py) and uncertainty tools (uncertainty.py)."""

import numpy as np
import pytest
from sklearn.calibration import CalibratedClassifierCV

from cardiostage.calibration import expected_calibration_error, make_variant
from cardiostage.data import get_features_and_target, load_clean, split_cleveland
from cardiostage.models import build_pipeline
from cardiostage.uncertainty import NoveltyDetector, SubsampleEnsemble, straddles


@pytest.fixture(scope="module")
def train():
    return split_cleveland(load_clean())[0]


# ------------------------------------------------------------- calibration --
def test_ece_near_zero_for_honest_probabilities():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 20_000)
    y = (rng.uniform(0, 1, p.size) < p).astype(int)  # outcomes drawn AT p
    assert expected_calibration_error(y, p) < 0.02


def test_ece_large_for_overconfident_probabilities():
    rng = np.random.default_rng(0)
    p_true = rng.uniform(0.3, 0.7, 20_000)
    y = (rng.uniform(0, 1, p_true.size) < p_true).astype(int)
    overconfident = np.where(p_true > 0.5, 0.95, 0.05)  # claims near-certainty
    assert expected_calibration_error(y, overconfident) > 0.2


def test_make_variant_wraps_and_clones():
    base = build_pipeline("logistic_regression", 1)
    assert make_variant(base, "uncalibrated") is not base
    assert isinstance(make_variant(base, "sigmoid"), CalibratedClassifierCV)


# ------------------------------------------------------------- uncertainty --
def test_straddles():
    low, high = np.array([0.1, 0.3, 0.05]), np.array([0.2, 0.4, 0.3])
    assert list(straddles(low, high, 0.25)) == [False, False, True]


def test_subsample_ensemble_interval(train):
    X, y = get_features_and_target(train, 1)
    ens = SubsampleEnsemble(build_pipeline("logistic_regression", 1), n_replicas=5).fit(X, y)
    low, high = ens.predict_interval(X.iloc[:10])
    assert ens.predict_all(X.iloc[:10]).shape == (5, 10)
    assert (low <= high).all() and (low >= 0).all() and (high <= 1).all()


def test_novelty_flags_implausible_patient_but_not_typical(train):
    X, _ = get_features_and_target(train, 1)
    detector = NoveltyDetector(1).fit(X)
    typical = X.median(numeric_only=True)
    patient = X.iloc[[0]].copy()
    for c in ["age", "trestbps", "chol"]:
        patient[c] = typical[c]
    weird = patient.copy()
    weird["age"], weird["chol"] = 19, 900  # far outside training data
    reasons = detector.check(weird)[0]
    assert any("age" in r for r in reasons) and any("chol" in r for r in reasons)
    assert detector.check(patient)[0] == []


def test_novelty_flags_about_one_percent_of_training(train):
    X, _ = get_features_and_target(train, 3)
    rate = NoveltyDetector(3).fit(X).is_unusual(X).mean()
    assert rate <= 0.03
