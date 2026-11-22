"""
The three candidate models, each wrapped in a full pipeline.

A scikit-learn Pipeline chains steps so they act like ONE model:

    raw patient columns --> [preprocessor] --> [classifier] --> prediction

Calling pipeline.fit(X_train, y_train) fits the preprocessor on the training
data and then trains the classifier on the preprocessed result. Calling
pipeline.predict(X_new) applies the SAME learned preprocessing to new data
before predicting. Because the preprocessor lives inside the pipeline, cross-
validation re-fits it inside every fold automatically, so there is no leakage.
"""

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from cardiostage import config
from cardiostage.preprocessing import build_preprocessor

MODEL_NAMES = ["logistic_regression", "random_forest", "xgboost"]

MODEL_LABELS = {
    "logistic_regression": "Logistic Regression",
    "random_forest": "Random Forest",
    "xgboost": "XGBoost",
}


def make_classifier(name: str):
    """Create an untrained classifier with sensible fixed settings."""
    if name == "logistic_regression":
        # Fits one weight per feature; prediction = sigmoid(weighted sum).
        # max_iter: allow enough optimisation steps to fully converge.
        return LogisticRegression(max_iter=5000)

    if name == "random_forest":
        # Hundreds of decision trees, each trained on a random sample of
        # patients and features; the forest averages their votes.
        return RandomForestClassifier(
            n_estimators=300,                # number of trees
            random_state=config.RANDOM_SEED,
            n_jobs=1,                        # parallelism happens one level up
        )

    if name == "xgboost":
        # Builds trees one after another, each correcting the previous
        # trees' mistakes ("gradient boosting").
        return XGBClassifier(
            eval_metric="logloss",
            random_state=config.RANDOM_SEED,
            n_jobs=1,
        )

    raise ValueError(f"Unknown model name: {name}")


# ---------------------------------------------------------------------------
# Hyperparameter grids
# ---------------------------------------------------------------------------
# "Hyperparameters" are settings WE choose before training (unlike the
# weights the model learns). The grid search tries every combination below
# and keeps the one with the best cross-validated score.
#
# Names are prefixed "model__" because the classifier is the step named
# "model" inside the pipeline (scikit-learn's naming convention).
#
# The grids are kept deliberately small: with ~240 training patients, a huge
# search would eventually find settings that fit the noise of our particular
# patients rather than real patterns (overfitting the search itself).
PARAM_GRIDS = {
    "logistic_regression": {
        # C = inverse regularisation strength. Small C = simpler model that
        # keeps weights small (more cautious); large C = trusts the data more.
        "model__C": [0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0],
    },
    "random_forest": {
        "model__max_depth": [3, 5, None],       # how many questions per tree
        "model__min_samples_leaf": [1, 5, 10],  # min patients per final group
        "model__max_features": ["sqrt", 0.5],   # features considered per split
    },
    "xgboost": {
        "model__n_estimators": [100, 300],      # number of boosting rounds
        "model__max_depth": [2, 3, 4],          # tree depth (shallow = simpler)
        "model__learning_rate": [0.03, 0.1],    # size of each correction step
        "model__min_child_weight": [1, 5],      # min evidence to make a split
        "model__subsample": [0.8],              # each tree sees 80% of patients
        "model__colsample_bytree": [0.8],       # ...and 80% of features
    },
}


def build_pipeline(name: str, stage: int) -> Pipeline:
    """Preprocessor for `stage` + the named classifier, as one estimator."""
    return Pipeline([
        ("preprocess", build_preprocessor(stage)),
        ("model", make_classifier(name)),
    ])
