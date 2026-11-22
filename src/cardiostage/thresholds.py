"""
Turning probabilities into decisions.

A model outputs a probability (e.g. 0.37). A decision needs a threshold:
"flag the patient if probability >= t". The threshold is a CHOICE, not
something the model learns, and in medicine it should reflect which mistake
is worse. These small, pure functions choose thresholds from data and are
tested directly in tests/test_staging.py.
"""

import math

import numpy as np


def threshold_for_recall(y_true, proba, target_recall: float) -> float:
    """
    The HIGHEST threshold that still catches at least `target_recall` of the
    sick patients.

    Why highest: lowering the threshold always catches more sick patients but
    also flags more healthy ones. We want the fewest false alarms that still
    meet the recall target.

    Example: 100 sick patients, target 0.90 -> we may miss at most 10.
    Sort the sick patients' probabilities from low to high; the threshold is
    the 11th lowest, so only the 10 below it are missed.
    """
    y_true = np.asarray(y_true)
    sick_scores = np.sort(np.asarray(proba)[y_true == 1])
    allowed_misses = math.floor((1 - target_recall) * len(sick_scores) + 1e-9)
    return float(sick_scores[allowed_misses])


def threshold_for_precision(y_true, proba, target_precision: float) -> float:
    """
    The LOWEST threshold at which at least `target_precision` of flagged
    patients are truly sick. Returns inf if no threshold achieves it (meaning:
    never confident enough to "rule in" at this stage).

    Why lowest: we want to confidently flag as MANY patients as possible
    while keeping the alarms trustworthy.
    """
    y_true = np.asarray(y_true)
    proba = np.asarray(proba)
    order = np.argsort(-proba)                 # highest probability first
    sorted_p, sorted_y = proba[order], y_true[order]
    true_pos = np.cumsum(sorted_y)             # sick patients flagged so far
    flagged = np.arange(1, len(sorted_y) + 1)  # total patients flagged so far
    precision = true_pos / flagged

    # A threshold must include ALL patients tied at that probability, so only
    # consider cut points at the last occurrence of each distinct value.
    is_cut = np.r_[sorted_p[1:] != sorted_p[:-1], True]
    valid = is_cut & (precision >= target_precision)
    if not valid.any():
        return float("inf")
    return float(sorted_p[np.flatnonzero(valid).max()])


def confusion_counts(y_true, y_pred) -> dict:
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    return {
        "tp": int(((y_pred == 1) & (y_true == 1)).sum()),
        "fp": int(((y_pred == 1) & (y_true == 0)).sum()),
        "fn": int(((y_pred == 0) & (y_true == 1)).sum()),
        "tn": int(((y_pred == 0) & (y_true == 0)).sum()),
    }


def decision_metrics(y_true, y_pred) -> dict:
    """
    recall      (sensitivity): of the sick, how many were flagged
    specificity              : of the healthy, how many were cleared
    precision   (PPV)        : of the flagged, how many are truly sick
    npv                      : of the cleared, how many are truly healthy
    """
    c = confusion_counts(y_true, y_pred)
    safe = lambda a, b: a / b if b else float("nan")
    return {
        "recall": safe(c["tp"], c["tp"] + c["fn"]),
        "specificity": safe(c["tn"], c["tn"] + c["fp"]),
        "precision": safe(c["tp"], c["tp"] + c["fp"]),
        "npv": safe(c["tn"], c["tn"] + c["fn"]),
        "accuracy": safe(c["tp"] + c["tn"], sum(c.values())),
        **c,
    }
