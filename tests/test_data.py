"""Tests for data cleaning (data.py) and preprocessing (preprocessing.py)."""

import numpy as np
import pandas as pd
import pytest

from cardiostage import config
from cardiostage.data import clean_data, get_features_and_target, load_raw
from cardiostage.preprocessing import build_preprocessor


# A pytest "fixture" builds something once and hands it to any test that asks
# for it by name, so every test below gets the cleaned data for free.
@pytest.fixture(scope="module")
def clean():
    return clean_data(load_raw())


# ---------------------------------------------------------------- cleaning --
def test_cleaning_does_not_modify_input():
    raw = load_raw()
    before = raw.copy()
    clean_data(raw)
    pd.testing.assert_frame_equal(raw, before)


def test_impossible_zeros_become_missing(clean):
    assert (clean["chol"] == 0).sum() == 0
    assert (clean["trestbps"] == 0).sum() == 0
    # All Swiss cholesterol values were zeros, so all must now be missing.
    swiss = clean[clean[config.HOSPITAL_COLUMN] == "Switzerland"]
    assert swiss["chol"].isna().all()


def test_duplicates_removed(clean):
    assert len(clean) == 918  # 920 raw rows minus 2 exact duplicates
    without_id = clean.drop(columns="id")
    assert not without_id.duplicated().any()


def test_binary_columns_are_zero_one(clean):
    for column in config.BINARY_FEATURES:
        values = set(clean[column].dropna().unique())
        assert values <= {0.0, 1.0}, f"{column} has values {values}"


def test_target_is_binary_and_matches_num(clean):
    assert set(clean[config.TARGET_COLUMN].unique()) == {0, 1}
    assert (clean[config.TARGET_COLUMN] == (clean["num"] > 0)).all()


def test_features_and_target_respect_stage(clean):
    X, y = get_features_and_target(clean, stage=1)
    assert list(X.columns) == config.STAGES[1]
    assert len(X) == len(y)


# ----------------------------------------------------------- preprocessing --
@pytest.mark.parametrize("stage", [1, 2, 3])
def test_preprocessor_output_is_complete_and_numeric(clean, stage):
    X, _ = get_features_and_target(clean, stage)
    out = build_preprocessor(stage).fit_transform(X)
    assert len(out) == len(X)
    assert not out.isna().any().any(), "preprocessor left missing values"
    assert all(np.issubdtype(dtype, np.number) for dtype in out.dtypes)


def test_stage1_expected_columns(clean):
    X, _ = get_features_and_target(clean, 1)
    out = build_preprocessor(1).fit_transform(X)
    # Stage 1 = 3 numeric (age, trestbps, chol) + 2 binary (sex, fbs)
    # + cp, whose 4 categories become 4 one-hot columns  ->  9 columns.
    assert out.shape[1] == 9
    assert "cp_asymptomatic" in out.columns


def test_preprocessor_learns_only_from_training_data(clean):
    """Fill values must come from the data the preprocessor was FIT on."""
    X, _ = get_features_and_target(clean, 1)
    train = X.iloc[:400]
    preprocessor = build_preprocessor(1).fit(train)
    imputer = preprocessor.named_transformers_["num"].named_steps["impute"]
    learned_chol_median = imputer.statistics_[list(imputer.feature_names_in_).index("chol")]
    assert learned_chol_median == pytest.approx(train["chol"].median())


def test_preprocessor_handles_new_patient_with_missing_and_unseen_values(clean):
    X, _ = get_features_and_target(clean, 3)
    preprocessor = build_preprocessor(3).fit(X)
    # A patient as the app might send: some tests not done, odd category.
    patient = X.iloc[[0]].copy()
    patient[["ca", "thal", "chol"]] = np.nan
    patient["restecg"] = "never-seen-before"
    out = preprocessor.transform(patient)
    assert not out.isna().any().any()
