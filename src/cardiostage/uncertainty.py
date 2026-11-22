"""
Knowing when NOT to trust a prediction. Two independent warning signs:

1. MODEL UNCERTAINTY (SubsampleEnsemble)
   "Would a slightly different set of training patients have changed the
   answer?" We train several copies of the model, each on a random 80% of
   the training patients. For a new patient, every copy gives a probability.
   If the copies agree (e.g. 61%-66%), the answer is stable. If they spread
   across a decision threshold (e.g. 9%-31% around a 17% cut-off), the
   decision depends on luck in our training sample, so we say so.

2. UNUSUAL PATIENTS (NoveltyDetector)
   "Has the model ever seen anyone like this?" A model can only learn from
   the patients it was shown. For a 29-year-old with cholesterol 590, it is
   extrapolating, and its probability is a guess, however precise it looks.
"""

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.base import clone
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline

from cardiostage import config
from cardiostage.preprocessing import build_preprocessor


def _fit_on_subsample(estimator, X, y, seed):
    rng = np.random.default_rng(seed)
    n = len(y)
    idx = rng.choice(n, size=int(config.REPLICA_FRACTION * n), replace=False)
    # Sampling WITHOUT replacement (unlike a bootstrap) means no patient
    # appears twice, which matters because the calibrators inside each copy
    # run their own cross-validation: a duplicated patient could land on
    # both sides of a split and make the copy overconfident.
    return clone(estimator).fit(X.iloc[idx], np.asarray(y)[idx])


class SubsampleEnsemble:
    def __init__(self, estimator, n_replicas=config.N_REPLICAS, seed=config.RANDOM_SEED):
        self.estimator = estimator
        self.n_replicas = n_replicas
        self.seed = seed

    def fit(self, X, y):
        # Train the copies in parallel on all CPU cores.
        self.replicas_ = Parallel(n_jobs=-1)(
            delayed(_fit_on_subsample)(self.estimator, X, y, self.seed + i)
            for i in range(self.n_replicas))
        return self

    def predict_all(self, X) -> np.ndarray:
        """Probabilities from every copy: shape (n_replicas, n_patients)."""
        return np.array([r.predict_proba(X)[:, 1] for r in self.replicas_])

    def predict_interval(self, X):
        """Middle range of the copies' probabilities, per patient."""
        low_pct, high_pct = config.UNCERTAINTY_PERCENTILES
        all_p = self.predict_all(X)
        return np.percentile(all_p, low_pct, axis=0), np.percentile(all_p, high_pct, axis=0)


def straddles(low, high, threshold) -> np.ndarray:
    """True where the uncertainty range crosses the threshold (decision could flip)."""
    return (np.asarray(low) < threshold) & (np.asarray(high) >= threshold)


class NoveltyDetector:
    """
    Two checks, each giving a human-readable reason:
      - RANGE: a measurement outside anything seen in training.
      - COMBINATION: an Isolation Forest scores how easy a patient is to
        "isolate" from the rest with random splits. Typical patients sit in
        crowded regions and take many splits; odd ones are isolated quickly.
        This catches strange combinations (e.g. age 30 with a maximum heart
        rate of 80) even when each value alone is within range.
    """

    def __init__(self, stage: int):
        self.stage = stage

    def fit(self, X: pd.DataFrame):
        self.features_ = list(X.columns)
        numeric = [c for c in config.NUMERIC_FEATURES if c in self.features_]
        self.ranges_ = {c: (X[c].min(), X[c].max()) for c in numeric}
        self.forest_ = Pipeline([
            ("preprocess", build_preprocessor(self.stage)),
            ("forest", IsolationForest(n_estimators=300, random_state=config.RANDOM_SEED)),
        ]).fit(X)
        # Higher score = more typical. The cut-off is set so that the most
        # unusual NOVELTY_QUANTILE of TRAINING patients fall below it.
        scores = self.forest_.score_samples(X)
        self.score_threshold_ = float(np.quantile(scores, config.NOVELTY_QUANTILE))
        return self

    def check(self, X: pd.DataFrame) -> list:
        """For each patient, a list of reasons it is unusual (empty = typical)."""
        X = X[self.features_]
        scores = self.forest_.score_samples(X)
        results = []
        for (_, row), score in zip(X.iterrows(), scores):
            reasons = []
            for column, (low, high) in self.ranges_.items():
                value = row[column]
                if pd.notna(value) and not (low <= value <= high):
                    reasons.append(f"{column} = {value:g} is outside the training range "
                                   f"({low:g} to {high:g})")
            if score < self.score_threshold_:
                reasons.append("unusual combination of values compared with training patients")
            results.append(reasons)
        return results

    def is_unusual(self, X: pd.DataFrame) -> np.ndarray:
        return np.array([bool(r) for r in self.check(X)])
