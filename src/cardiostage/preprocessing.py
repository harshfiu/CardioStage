"""
Turning cleaned patient data into the all-numeric, no-gaps table models need.

Machine-learning models need inputs that are:
  1. complete:  no missing values (most models crash on NaN),
  2. numeric:   no text like "atypical angina",
  3. on comparable scales, for some models (logistic regression).

The key idea: this is built as a scikit-learn *transformer* that is FIT on
training data only, then APPLIED to any new data. For example, missing
cholesterol is filled with the median of the TRAINING patients, and that same
number is reused for test patients and for real users of the app later.
"""

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from cardiostage import config


def build_preprocessor(stage: int) -> ColumnTransformer:
    """
    Build an (unfitted) preprocessor for the features available at `stage`.

    A ColumnTransformer sends different groups of columns through different
    preparation steps, then glues the results back into one table.
    """
    stage_features = set(config.STAGES[stage])

    # Keep only the columns of each type that exist at this stage.
    # (Preserving the order defined in config keeps outputs predictable.)
    numeric = [c for c in config.NUMERIC_FEATURES if c in stage_features]
    binary = [c for c in config.BINARY_FEATURES if c in stage_features]
    categorical = [c for c in config.CATEGORICAL_FEATURES if c in stage_features]

    # --- Numeric columns: fill gaps, then standardise -----------------------
    # SimpleImputer(strategy="median") fills NaN with the column's median
    # (the middle value). We use the median rather than the mean because it
    # isn't dragged around by a few extreme values (e.g. cholesterol of 603).
    #
    # StandardScaler rescales each column to mean 0 and standard deviation 1.
    # Why: logistic regression is sensitive to scale. Cholesterol (~200) would
    # otherwise dwarf ST depression (~1) in its calculations. Tree models
    # (random forest, XGBoost) don't care, and scaling doesn't hurt them.
    numeric_pipeline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )

    # --- Binary columns: fill gaps with the most common value ---------------
    # They're already 0/1, so no scaling needed. A median of 0/1 data isn't
    # meaningful, so we use the most frequent value instead.
    binary_pipeline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="most_frequent")),
        ]
    )

    # --- Categorical columns: fill gaps, then one-hot encode ----------------
    # One-hot encoding turns a column like cp (4 chest-pain types) into four
    # yes/no columns: cp_asymptomatic, cp_atypical angina, ... with exactly one
    # set to 1 per patient. We can't just number them 1-4, because the model
    # would wrongly assume "type 4 is twice type 2".
    #
    # handle_unknown="ignore": if the app ever receives a category never seen
    # in training, encode it as all-zeros instead of crashing.
    # sparse_output=False: return a normal table rather than a compressed one,
    # which keeps things simple and readable at our small data size.
    categorical_pipeline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, numeric),
            ("bin", binary_pipeline, binary),
            ("cat", categorical_pipeline, categorical),
        ],
        # Feature names like "num__chol" are awkward; drop the prefixes so
        # outputs read as "chol", "cp_asymptomatic", etc. (useful for SHAP).
        verbose_feature_names_out=False,
    )

    # Return a pandas DataFrame (with column names) instead of a bare array,
    # so we can always see which number belongs to which feature.
    preprocessor.set_output(transform="pandas")
    return preprocessor
