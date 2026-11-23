"""
Small statistics helpers shared by the evaluation phases.

Every number we report from small groups (61 test patients, 78 women, 8
healthy Swiss patients...) comes with a confidence interval, because a single
number from a small group can be very misleading on its own.
"""

import re

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


def exact_proportion_ci(successes: int, total: int, level: float = 0.95):
    """
    Clopper-Pearson ("exact") confidence interval for a proportion, such as
    recall = sick patients caught / all sick patients.

    Why not the bootstrap here? With 28 of 28 caught, every bootstrap resample
    also has 0 misses, so the bootstrap claims [1.000, 1.000], i.e. certainty.
    But a true recall of, say, 92% would still produce 28/28 fairly often. The
    exact interval asks: "which true rates make the observed count plausible?"
    For 28/28 the answer is roughly 88%-100%.

    Returns (estimate, low, high).
    """
    from scipy.stats import beta

    alpha = 1 - level
    low = 0.0 if successes == 0 else beta.ppf(alpha / 2, successes, total - successes + 1)
    high = 1.0 if successes == total else beta.ppf(1 - alpha / 2, successes + 1, total - successes)
    return successes / total, float(low), float(high)


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


def parse_ci(text: str) -> dict:
    """Read back a formatted interval: '0.965 [0.928, 0.992]' -> {'value', 'low', 'high'}."""
    value, low, high = (float(x) for x in re.findall(r"-?\d+\.\d+", str(text))[:3])
    return {"value": value, "low": low, "high": high}
