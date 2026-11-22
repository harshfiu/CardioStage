"""
Loading and cleaning the raw heart-disease data.

This module answers one question: "how do we turn the messy raw CSV into a
trustworthy table?" Every fix below is based on something we actually found
when exploring the data (see docs/learning/02-data.md for the evidence).

What this module deliberately does NOT do: fill in missing values or convert
text categories into numbers. Those steps must be "learned" from training
data only, so they live in preprocessing.py inside the model pipeline.
Doing them here, on the full dataset, would leak information from the test
set into training (explained in the learning guide).

Run directly to produce data/processed/heart_clean.csv:
    python -m cardiostage.data
"""

import numpy as np
import pandas as pd

from cardiostage import config


def load_raw() -> pd.DataFrame:
    """Read the original CSV exactly as downloaded."""
    return pd.read_csv(config.RAW_DATA_PATH)


def clean_data(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Apply every data-quality fix and return a NEW cleaned DataFrame.

    The input is never modified (we work on a copy). Functions that silently
    change their inputs are a classic source of confusing bugs.
    """
    df = raw.copy()

    # --- Fix 1: impossible zeros are really "not measured" ------------------
    # A living person cannot have a cholesterol of 0 or a blood pressure of 0.
    # In this dataset ALL 123 Swiss patients (and 49 VA patients) have chol = 0:
    # those hospitals simply didn't record it and stored 0 instead of blank.
    # Leaving the zeros in would teach the model "cholesterol 0 = very sick"
    # (most Swiss patients are sick), which is medically absurd.
    # np.nan is pandas' marker for "missing value".
    for column in ["chol", "trestbps"]:
        df.loc[df[column] == 0, column] = np.nan

    # NOTE: oldpeak (ST depression) is legitimately 0 for many patients
    # (a normal ECG under stress), and the 12 negative values (mostly Swiss)
    # describe ST *elevation*, which is a real ECG finding. So we keep both.

    # --- Fix 2: remove exact duplicate patients -----------------------------
    # Two pairs of rows are identical in every column except the id. If one
    # copy landed in training and the other in testing, the model would be
    # "tested" on a patient it had already memorised, inflating the score.
    feature_and_target_columns = [c for c in df.columns if c != "id"]
    df = df.drop_duplicates(subset=feature_and_target_columns, keep="first")

    # --- Fix 3: consistent yes/no columns -----------------------------------
    # fbs and exang were read as a mix of True/False/missing (Python objects).
    # sex is the text "Male"/"Female". Convert all three to 1.0 / 0.0, keeping
    # missing values as NaN. (Floats, because integers can't hold NaN.)
    df["sex"] = df["sex"].map({"Male": 1.0, "Female": 0.0})
    for column in ["fbs", "exang"]:
        df[column] = df[column].map({True: 1.0, False: 0.0})

    # --- Fix 4: the prediction target ---------------------------------------
    # num: 0 = no disease, 1-4 = increasing severity. We answer yes/no, so
    # anything above 0 becomes 1. We keep num itself for reference only.
    df[config.TARGET_COLUMN] = (df[config.RAW_TARGET_COLUMN] > 0).astype(int)

    return df.reset_index(drop=True)


def get_features_and_target(df: pd.DataFrame, stage: int):
    """
    Split a cleaned table into X (model inputs) and y (the answer to predict),
    using only the features available at the given stage.

    By ML convention, X is the table of inputs and y is the column of answers.
    """
    X = df[config.STAGES[stage]]
    y = df[config.TARGET_COLUMN]
    return X, y


def save_clean_data(df: pd.DataFrame) -> None:
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.CLEAN_DATA_PATH, index=False)


if __name__ == "__main__":
    # This block runs only when the file is executed directly
    # (python -m cardiostage.data), not when it's imported by another file.
    raw = load_raw()
    clean = clean_data(raw)
    save_clean_data(clean)
    print(f"Raw rows: {len(raw)}  ->  clean rows: {len(clean)}")
    print(f"Saved to {config.CLEAN_DATA_PATH}")
