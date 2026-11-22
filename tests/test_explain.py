"""Tests for SHAP explanations (explain.py)."""

import numpy as np
import pytest

from cardiostage import config
from cardiostage.data import get_features_and_target, load_clean, split_cleveland
from cardiostage.explain import StageExplainer, explanation_text, format_value
from cardiostage.models import build_pipeline


@pytest.fixture(scope="module")
def setup():
    train, _ = split_cleveland(load_clean())
    X, y = get_features_and_target(train, 2)
    model = build_pipeline("logistic_regression", 2).fit(X, y)
    return train, model, StageExplainer(model, config.STAGES[2], train)


def test_encode_decode_roundtrip(setup):
    train, _, explainer = setup
    X = train[config.STAGES[2]].head(20)
    back = explainer.decode(explainer.encode(X))
    for c in X.columns:
        original, restored = X[c].reset_index(drop=True), back[c]
        assert ((original == restored) | (original.isna() & restored.isna())).all(), c


def test_explanations_add_up_to_prediction(setup):
    train, model, explainer = setup
    patients = train.head(5)
    e = explainer.explain(patients)
    predicted = model.predict_proba(patients[config.STAGES[2]])[:, 1]
    np.testing.assert_allclose(e.base_values + e.values.sum(axis=1), predicted, atol=1e-6)


def test_baseline_close_to_training_average(setup):
    train, model, explainer = setup
    e = explainer.explain(train.head(1))
    avg = model.predict_proba(train[config.STAGES[2]])[:, 1].mean()
    assert abs(e.base_values[0] - avg) < 0.05


def test_describe_sorted_by_impact_and_text(setup):
    train, model, explainer = setup
    patient = train.head(1)
    e = explainer.explain(patient)
    table = explainer.describe(patient.iloc[0], e[0])
    impacts = table["contribution"].abs().to_numpy()
    assert (impacts[:-1] >= impacts[1:]).all()
    text = explanation_text(table, e.base_values[0], 0.5)
    assert text.startswith("Estimated risk 50%")


def test_format_value():
    assert format_value("sex", 0.0) == "female"
    assert format_value("thalch", 152.0) == "152 bpm"
    assert format_value("chol", np.nan) == "not measured"
    assert format_value("cp", "asymptomatic") == "no chest pain"
