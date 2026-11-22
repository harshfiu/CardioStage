"""
Sanity checks for the project setup.

Run with:  pytest
pytest finds every function whose name starts with `test_` and runs it.
If an `assert` statement is False, that test fails and tells you why.
These checks catch problems early, e.g. the wrong dataset version
(the 303-row Cleveland-only file instead of the 920-row combined one).
"""

import pandas as pd

from cardiostage import config


def test_raw_data_exists():
    assert config.RAW_DATA_PATH.exists(), (
        f"Dataset not found at {config.RAW_DATA_PATH}. "
        "Download heart_disease_uci.csv from Kaggle into data/raw/."
    )


def test_raw_data_shape_and_columns():
    df = pd.read_csv(config.RAW_DATA_PATH)

    # 920 patients across 4 hospitals, 16 columns.
    assert df.shape == (920, 16)

    # Every feature we assigned to a stage must really exist in the data.
    for column in config.STAGES[3]:
        assert column in df.columns, f"Missing feature column: {column}"

    assert config.RAW_TARGET_COLUMN in df.columns
    assert config.HOSPITAL_COLUMN in df.columns


def test_all_four_hospitals_present():
    df = pd.read_csv(config.RAW_DATA_PATH)
    hospitals = set(df[config.HOSPITAL_COLUMN].unique())
    assert hospitals == {"Cleveland", "Hungary", "Switzerland", "VA Long Beach"}


def test_stages_are_nested():
    # Each stage must contain everything from the previous stage
    # (a patient who had a treadmill test still has their basic info).
    assert set(config.STAGES[1]) < set(config.STAGES[2]) < set(config.STAGES[3])
    # And there are 13 patient features in total, none duplicated.
    assert len(config.STAGES[3]) == len(set(config.STAGES[3])) == 13
