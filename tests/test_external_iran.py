"""
Tests for the Iranian external cohort (cardiostage.external_iran): the data
file is the published one, and every mapping rule does what its docstring says.
None need the trained models.
"""

import hashlib

import numpy as np
import pandas as pd
import pytest

from cardiostage import config, external_iran
from cardiostage.predictor import CardioStagePredictor


@pytest.fixture(scope="module")
def raw():
    return external_iran.load_iran()


@pytest.fixture(scope="module")
def mapped(raw):
    return external_iran.to_cardiostage(raw)


def test_data_file_is_the_published_conversion():
    digest = hashlib.sha256(external_iran.IRAN_DATA_PATH.read_bytes()).hexdigest()
    assert digest == "88a89ea916f6e2f62617d033a46fbd782e2e710f26569e53185679edcdcaca2b"


def test_shape_and_outcome(raw, mapped):
    assert raw.shape == (303, 56) and raw.isna().sum().sum() == 0
    assert mapped[config.TARGET_COLUMN].sum() == 216  # 216 CAD, 87 Normal


def test_chest_pain_mapping(raw, mapped):
    assert mapped["cp"].value_counts().to_dict() == {
        "typical angina": 164,
        "atypical angina": 93,
        "asymptomatic": 30,
        "non-anginal": 16,
    }
    # The source columns never mark two types at once (so the order of rules can't matter).
    assert not ((raw["Typical Chest Pain"] == 1) & (raw["Atypical"] == "Y")).any()


def test_cholesterol_estimate(raw, mapped):
    estimate = raw["LDL"] + raw["HDL"] + raw["TG"] / 5
    ok = (raw["TG"] < 400) & estimate.between(80, 700)
    assert np.allclose(mapped.loc[ok, "chol"], estimate[ok])
    assert mapped.loc[~ok, "chol"].isna().all()
    assert (raw["TG"] >= 400).sum() == 5 and (~ok).sum() == 7  # 5 high-TG + 2 implausible


def test_other_mappings(raw, mapped):
    assert set(mapped["sex"].unique()) == {0.0, 1.0}
    assert (mapped["fbs"] == (raw["FBS"] > 120)).all()
    assert (mapped.loc[raw["LVH"] == "Y", "restecg"] == "lv hypertrophy").all()
    for col in ("thalch", "exang", "oldpeak", "slope", "ca", "thal"):
        assert mapped[col].isna().all()  # not available in this cohort


def test_every_patient_passes_the_apps_input_validation(mapped):
    """The mapped values must be valid CardioStage inputs (same validation as the app)."""
    features = config.STAGES[1]
    for record in mapped[features].to_dict("records"):
        frame = CardioStagePredictor.to_frame(record, features)
        assert list(frame.columns) == features
    assert isinstance(mapped, pd.DataFrame)
