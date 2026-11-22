"""Tests for stats.py (confidence intervals and prior shift) and fairness helpers."""

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from cardiostage.fairness import age_band, recall, specificity
from cardiostage.stats import bootstrap_ci, prior_shift


def test_bootstrap_ci_contains_estimate_and_narrows_with_more_data():
    rng = np.random.default_rng(1)
    small = rng.normal(size=30)
    large = rng.normal(size=3000)
    est_s, lo_s, hi_s = bootstrap_ci(np.mean, small)
    est_l, lo_l, hi_l = bootstrap_ci(np.mean, large)
    assert lo_s <= est_s <= hi_s and lo_l <= est_l <= hi_l
    assert (hi_l - lo_l) < (hi_s - lo_s)


def test_bootstrap_ci_skips_single_class_resamples():
    y = np.array([0] * 40 + [1] * 2)       # very few positives
    p = np.linspace(0, 1, 42)
    est, lo, hi = bootstrap_ci(roc_auc_score, y, p, need_both_classes=True)
    assert est == pytest.approx(1.0)        # resamples without a positive were skipped, no crash


def test_prior_shift_no_change_when_rates_equal():
    p = np.array([0.1, 0.5, 0.9])
    np.testing.assert_allclose(prior_shift(p, 0.4, 0.4), p, atol=1e-9)


def test_prior_shift_moves_toward_new_rate_and_keeps_order():
    p = np.array([0.1, 0.3, 0.6])
    shifted = prior_shift(p, train_rate=0.46, new_rate=0.93)
    assert (shifted > p).all()                     # higher local disease rate -> higher risk
    assert list(np.argsort(shifted)) == [0, 1, 2]  # ranking unchanged
    # Bayes check on one value: odds 0.5/0.5=1, factor = (0.93/0.07)/(0.46/0.54)
    factor = (0.93 / 0.07) / (0.46 / 0.54)
    assert prior_shift([0.5], 0.46, 0.93)[0] == pytest.approx(factor / (1 + factor))


def test_recall_specificity_helpers():
    y = np.array([1, 1, 0, 0])
    d = np.array([1, 0, 0, 1])
    assert recall(y, d) == 0.5 and specificity(y, d) == 0.5


def test_age_bands():
    bands = age_band(pd.Series([35, 49, 50, 59, 60, 77])).astype(str).tolist()
    assert bands == ["under 50", "under 50", "50-59", "50-59", "60+", "60+"]
