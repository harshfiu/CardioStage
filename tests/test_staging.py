"""Tests for threshold selection (thresholds.py) and the staged policy (staging.py)."""

import numpy as np
import pytest

from cardiostage.staging import simulate_policy
from cardiostage.thresholds import (decision_metrics, threshold_for_precision,
                                    threshold_for_recall)

RNG = np.random.default_rng(0)


@pytest.fixture
def synthetic():
    # 200 patients; sick ones tend to get higher scores, with overlap.
    y = np.r_[np.ones(100), np.zeros(100)].astype(int)
    p = np.r_[RNG.beta(5, 2, 100), RNG.beta(2, 5, 100)]
    return y, p


@pytest.mark.parametrize("target", [0.80, 0.90, 0.95, 0.97])
def test_threshold_for_recall_meets_target(synthetic, target):
    y, p = synthetic
    t = threshold_for_recall(y, p, target)
    assert decision_metrics(y, (p >= t).astype(int))["recall"] >= target


def test_threshold_for_recall_is_the_highest_possible(synthetic):
    y, p = synthetic
    t = threshold_for_recall(y, p, 0.90)
    # Any higher threshold (the next sick score up) must break the target.
    higher = np.sort(p[y == 1])
    higher = higher[higher > t][0]
    assert decision_metrics(y, (p >= higher).astype(int))["recall"] < 0.90


def test_threshold_for_precision_meets_target(synthetic):
    y, p = synthetic
    t = threshold_for_precision(y, p, 0.90)
    assert decision_metrics(y, (p >= t).astype(int))["precision"] >= 0.90


def test_threshold_for_precision_unreachable_returns_inf():
    y = np.array([0, 1, 0, 1])
    p = np.array([0.9, 0.8, 0.7, 0.6])  # the top-scored patient is healthy
    assert threshold_for_precision(y, p, 0.99) == float("inf")


def test_decision_metrics_hand_example():
    # The confusion-matrix example from the Phase 3 guide.
    y = np.r_[np.ones(46), np.zeros(54)]
    pred = np.r_[np.ones(36), np.zeros(10), np.ones(6), np.zeros(48)]
    m = decision_metrics(y, pred)
    assert (m["tp"], m["fn"], m["fp"], m["tn"]) == (36, 10, 6, 48)
    assert m["recall"] == pytest.approx(36 / 46)
    assert m["precision"] == pytest.approx(36 / 42)


def test_policy_routes_patients_correctly():
    zones = {1: {"rule_out_below": 0.2, "rule_in_from": 0.8},
             2: {"rule_out_below": 0.3, "rule_in_from": 0.7},
             3: {"screening_threshold": 0.5}}
    # patient 0: stage-1 low; 1: stage-1 high; 2: decided at stage 2 (high);
    # 3: reaches stage 3 and is flagged; 4: reaches stage 3 and is cleared.
    p = {1: np.array([0.1, 0.9, 0.5, 0.5, 0.5]),
         2: np.array([0.9, 0.1, 0.75, 0.5, 0.5]),
         3: np.array([0.9, 0.1, 0.1, 0.6, 0.4])}
    decision, stopped = simulate_policy(p, zones)
    assert list(decision) == [0, 1, 1, 1, 0]
    assert list(stopped) == [1, 1, 2, 3, 3]
