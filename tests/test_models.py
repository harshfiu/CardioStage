"""Tests for the data split, model pipelines and the from-scratch model."""

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from cardiostage import config
from cardiostage.data import get_features_and_target, load_clean, split_cleveland
from cardiostage.from_scratch import ScratchLogisticRegression, sigmoid
from cardiostage.models import MODEL_NAMES, build_pipeline
from cardiostage.preprocessing import build_preprocessor


@pytest.fixture(scope="module")
def split():
    return split_cleveland(load_clean())


# ------------------------------------------------------------------ split --
def test_split_is_cleveland_only_and_disjoint(split):
    train, test = split
    assert set(train[config.HOSPITAL_COLUMN]) == {"Cleveland"}
    assert set(test[config.HOSPITAL_COLUMN]) == {"Cleveland"}
    assert set(train["id"]).isdisjoint(test["id"])  # no patient in both
    assert len(train) + len(test) == 304


def test_split_is_reproducible_and_stratified(split):
    train, test = split
    train2, test2 = split_cleveland(load_clean())
    assert list(test["id"]) == list(test2["id"])  # same sealed test set every time
    gap = abs(train[config.TARGET_COLUMN].mean() - test[config.TARGET_COLUMN].mean())
    assert gap < 0.02


# --------------------------------------------------------------- pipelines --
@pytest.mark.parametrize("name", MODEL_NAMES)
def test_every_pipeline_trains_and_predicts_probabilities(split, name):
    train, test = split
    X, y = get_features_and_target(train, 3)
    model = build_pipeline(name, 3).fit(X, y)
    proba = model.predict_proba(get_features_and_target(test, 3)[0])[:, 1]
    assert proba.shape == (len(test),)
    assert ((proba >= 0) & (proba <= 1)).all()


# ------------------------------------------------------------ from scratch --
def test_sigmoid_basic_values():
    assert sigmoid(0) == pytest.approx(0.5)
    assert sigmoid(100) == pytest.approx(1.0)
    assert sigmoid(-100) == pytest.approx(0.0)


def test_scratch_loss_decreases(split):
    train, _ = split
    X_raw, y = get_features_and_target(train, 3)
    X = build_preprocessor(3).fit_transform(X_raw)
    model = ScratchLogisticRegression(C=0.1).fit(X, y)
    assert model.loss_history[-1] < model.loss_history[0]


def test_scratch_matches_scikit_learn(split):
    train, _ = split
    X_raw, y = get_features_and_target(train, 3)
    X = build_preprocessor(3).fit_transform(X_raw)
    ours = ScratchLogisticRegression(C=0.1).fit(X, y)
    theirs = LogisticRegression(C=0.1, max_iter=5000, tol=1e-10).fit(X, y)
    np.testing.assert_allclose(ours.weights, theirs.coef_[0], atol=1e-4)
    assert ours.bias == pytest.approx(theirs.intercept_[0], abs=1e-4)
