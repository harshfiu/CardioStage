"""
Tests for the v2.0 pooled dataset and its new sealed test split
(cardiostage.pooled). None need the trained models.
"""

import pytest

from cardiostage import config, pooled


@pytest.fixture(scope="module")
def data():
    return pooled.load_pooled()


@pytest.fixture(scope="module")
def split(data):
    return pooled.split_v2(data)


def test_pooled_has_all_five_hospitals(data):
    counts = data[config.HOSPITAL_COLUMN].value_counts().to_dict()
    assert counts == {
        "Cleveland": 304,
        "Iran": 303,
        "Hungary": 292,
        "VA Long Beach": 199,
        "Switzerland": 123,
    }
    assert set(data.columns) == set(config.STAGES[3]) | {
        config.TARGET_COLUMN,
        config.HOSPITAL_COLUMN,
    }


def test_sealed_test_is_20_percent_of_every_hospital(data, split):
    train, test = split
    assert len(train) + len(test) == len(data)
    assert not set(train.index) & set(test.index)  # no patient in both
    for h, n in data[config.HOSPITAL_COLUMN].value_counts().items():
        n_test = (test[config.HOSPITAL_COLUMN] == h).sum()
        assert abs(n_test - 0.2 * n) <= 1.5, h


def test_split_is_stratified_by_outcome(data, split):
    _, test = split
    for h in pooled.HOSPITALS:
        full = data.loc[data[config.HOSPITAL_COLUMN] == h, config.TARGET_COLUMN].mean()
        held = test.loc[test[config.HOSPITAL_COLUMN] == h, config.TARGET_COLUMN].mean()
        assert abs(full - held) < 0.06, h


def test_split_is_reproducible(data, split):
    again_train, again_test = pooled.split_v2(data)
    assert list(again_test.index) == list(split[1].index)


def test_stage_hospitals(data):
    assert set(pooled.stage_data(data, 1)[config.HOSPITAL_COLUMN]) == set(pooled.HOSPITALS)
    assert "Iran" not in set(pooled.stage_data(data, 2)[config.HOSPITAL_COLUMN])  # no exercise test
    assert set(pooled.stage_data(data, 3)[config.HOSPITAL_COLUMN]) == {"Cleveland"}


def test_cleveland_split_is_exactly_v1s(data, split):
    """No v2 test patient may have trained v1's stage-2/3 models (leakage)."""
    import pandas as pd

    from cardiostage.data import load_clean, split_cleveland

    uci = load_clean()
    _, v1_test = split_cleveland(uci)
    _, test = split
    v2_cle = test[test[config.HOSPITAL_COLUMN] == "Cleveland"]
    assert len(v2_cle) == len(v1_test) == 61
    assert sorted(v2_cle.index) == sorted(v1_test.index)  # the same patients...
    cols = config.STAGES[3] + [config.TARGET_COLUMN]
    pd.testing.assert_frame_equal(  # ...with the same values
        v2_cle.loc[v1_test.index, cols], v1_test[cols], check_dtype=False
    )
