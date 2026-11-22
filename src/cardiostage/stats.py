"""
Small statistics helpers shared by the evaluation phases.

Every number we report from small groups (61 test patients, 78 women, 8
healthy Swiss patients...) comes with a confidence interval, because a single
number from a small group can be very misleading on its own.
"""

import numpy as np

from cardiostage import config


def bootstrap_ci(metric, *arrays, n_boot: int = 1000, need_both_classes: bool = False):
    """
    Point estimate and 95% bootstrap confidence interval of metric(*arrays).

    arrays are aligned per patient (e.g. y, proba). Each resample draws
    patients with replacement. If need_both_classes is True (e.g. ROC-AUC,
    which needs sick AND healthy patients), resamples lacking one class are
    skipped.

    Returns (estimate, low, high). Low/high are NaN if too few valid resamples.
    """
    arrays = [np.asarray(a) for a in arrays]
    estimate = metric(*arrays)
    rng = np.random.default_rng(config.RANDOM_SEED)
    n = len(arrays[0])
    values = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if need_both_classes and len(np.unique(arrays[0][idx])) < 2:
            continue
        values.append(metric(*(a[idx] for a in arrays)))
    if len(values) < n_boot * 0.5:
        return estimate, np.nan, np.nan
    return estimate, float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


def fmt_ci(estimate, low, high, digits: int = 3) -> str:
    if np.isnan(low):
        return f"{estimate:.{digits}f}"
    return f"{estimate:.{digits}f} [{low:.{digits}f}, {high:.{digits}f}]"


def prior_shift(proba, train_rate: float, new_rate: float):
    """
    Adjust probabilities for a hospital whose disease rate differs from the
    training hospital's, using Bayes' rule on the odds:

        new odds = old odds x (new-hospital odds / training odds)

    Intuition: if 93% of a clinic's patients are sick (vs 46% in training),
    every patient there starts with a much higher "before any tests" chance,
    and the model's output should shift up accordingly. This needs only the
    local disease rate, not any local training data.
    """
    p = np.clip(np.asarray(proba), 1e-6, 1 - 1e-6)
    odds = p / (1 - p)
    factor = (new_rate / (1 - new_rate)) / (train_rate / (1 - train_rate))
    new_odds = odds * factor
    return new_odds / (1 + new_odds)
